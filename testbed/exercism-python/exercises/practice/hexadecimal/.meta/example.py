from functools import reduce


def hexa(hex_string):
    hex_string = hex_string.lower()
    if set(hex_string) - set('0123456789abcdef'):
        raise ValueError('Invalid hexadecimal string')
    digits = [ord(letter) - ord('a') + 10 if letter in 'abcdef' else ord(letter) - ord('0')
              for letter in hex_string]
    return reduce(lambda var_1, var_2: var_1 * 16 + var_2, digits, 0)
