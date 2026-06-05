import os

# Specify the root directory of your project
project_dir = ["src", "proto"]  # Adjust this to your project folder

# Output file where all code will be combined
output_file = "./scripts/combined_code.txt"

# Function to combine files
def combine_files(root_dir, output_file):
    with open(output_file, "w") as outfile:
        for dir in root_dir:
            for subdir, _, files in os.walk(dir):
                for file in files:
                    if file.endswith(".cpp") or file.endswith(".h") or file.endswith(".proto") or file.endswith(".hpp"):  # Change this for other file types
                        file_path = os.path.join(subdir, file)
                        with open(file_path, "r") as infile:
                            outfile.write(f"// Start of {file_path}\n")
                            outfile.write(infile.read())
                            outfile.write(f"\n// End of {file_path}\n\n")
        print(f"All files combined into {output_file}")

# Combine all files
combine_files(project_dir, output_file)