#!/usr/bin/env python3
import os


def main():
    st = os.statvfs("/")
    used = st.f_blocks - st.f_bfree
    print(round(used / st.f_blocks * 100) if st.f_blocks else 0)


if __name__ == "__main__":
    main()
