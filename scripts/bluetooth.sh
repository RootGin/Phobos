#!/usr/bin/env bash

# Taken from Tail-R. Thanks man love your stuff.

ewwPath=$(pwd)

get_device_name() {
    if [ "$(get_con_status)" == "connected" ]; then
        knownDeviceNumber=$(bluetoothctl devices | awk '{print $2}')

        for deviceNumber in $knownDeviceNumber; do
            if [ "$(bluetoothctl info $deviceNumber | grep Connected: | awk '{print $2}')" == "yes" ]; then
                echo $(bluetoothctl info $deviceNumber | grep Name: | awk '{for (i = 2; i <= NF; i++) {printf "%s ", $i}; printf "\n"}') 
                return
            fi
        done
    fi
        
    echo "--"
}

get_con_status() {
    if bluetoothctl devices Connected | grep -q .; then
        echo "connected"
        return
    fi

    echo "disabled"
}

toggle() {
    if [ "$(get_con_status)" == "connected" ]; then
        bluetoothctl disconnect
    else
        knownDeviceNumber=$(bluetoothctl devices | awk '{print $2}')
        
        for deviceNumber in $knownDeviceNumber; do
            bluetoothctl connect $deviceNumber 
        done    
    fi  
}

update_eww_json() {
    deviceNameList=$(bluetoothctl devices | awk '{print $2}')

    # Create json array
    deviceNameListJson=[\"$(echo $deviceNameList | sed -e 's/ /", "/g')\"]
    eww -c $ewwPath update JSON_BT_DEVNAME="$deviceNameListJson"
}

# Main
if [ "$1" == "--con_status" ]; then
    get_con_status
elif [ "$1" == "--devname" ]; then
    get_device_name
elif [ "$1" == "--toggle" ]; then
    toggle
elif [ "$1" == "--update_eww_json" ]; then
    update_eww_json
fi
