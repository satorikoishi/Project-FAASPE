import random

def generate_random_ints_and_average():
    # Generate 10 random integers between 0 and 100
    random_ints = [random.randint(0, 10000) for _ in range(10)]
    
    # Concatenate integers into a single string, using space as a delimiter
    concatenated_string = ' '.join(str(num) for num in random_ints)
    print("Concatenated string of integers:", concatenated_string)
    
    # Split the concatenated string by space to extract the integers
    extracted_ints = [int(num) for num in concatenated_string.split()]
    
    # Calculate the average of these integers
    average = sum(extracted_ints) / len(extracted_ints)
    print("Extracted integers:", extracted_ints)
    print("Average of extracted integers:", average)
    
    return average

# Call the function
generate_random_ints_and_average()