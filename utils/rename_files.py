import os

def clean_filename(filename):
    # Convert to lowercase
    new_name = filename.lower()
    
    # Remove commas and apostrophes
    new_name = new_name.replace(',', '').replace("'", '')
    
    # Replace spaces with hyphens
    new_name = new_name.replace(' ', '-')
    
    return new_name

def rename_files():
    # Get the current directory
    current_dir = os.getcwd()
    
    # List all files in the current directory
    files = os.listdir(current_dir)
    
    for filename in files:
        # Skip the script itself
        if filename == os.path.basename(__file__):
            continue
            
        # Generate new filename
        new_filename = clean_filename(filename)
        
        # Skip if the filename is already in the desired format
        if filename == new_filename:
            continue
            
        # Create full file paths
        old_filepath = os.path.join(current_dir, filename)
        new_filepath = os.path.join(current_dir, new_filename)
        
        try:
            os.rename(old_filepath, new_filepath)
            print(f'Renamed: {filename} → {new_filename}')
        except Exception as e:
            print(f'Error renaming {filename}: {str(e)}')

if __name__ == '__main__':
    print('Starting file renaming process...')
    rename_files()
    print('Finished renaming files.') 