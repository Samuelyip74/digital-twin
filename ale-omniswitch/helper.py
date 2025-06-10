import os
import sys
import re
import random

def generate_random_mac():
    return "02:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}".format(
        random.randint(0x00, 0x7f),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff),
        random.randint(0x00, 0xff)
    )



