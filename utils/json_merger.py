import json

def merge_json_files():
    with open('data/json/cse_pdf_data.json', 'r', encoding='utf-8') as file:
        data = json.load(file)

    with open('data/json/cse_website_data.json', 'r', encoding='utf-8') as file:
        website_data = json.load(file)

    website_dict = {item['course_code']: item['website'] for item in website_data}

    for course in data:
        course_code = course['course_code']
        if course_code in website_dict:
            course['website'] = website_dict[course_code]

    with open('data/json/cse_merged_data.json', 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    try:
        merge_json_files()
        print("Successfully merged JSON files. Output saved to 'merged_data.json'")
    except Exception as e:
        print(f"An error occurred: {str(e)}")