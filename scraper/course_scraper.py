import requests
from bs4 import BeautifulSoup
import json
import time
import re

def get_urls():
    with open('course_urls_formatted.txt', 'r') as file:
        return [line.strip() for line in file if line.strip()]

def extract_course_code(url):
    match = re.search(r'-([a-zA-Z]+\d+)$', url)
    return match.group(1).upper() if match else None

def get_text_or_none(element):
    return element.get_text(strip=True) if element else ""

def parse_period_value(period_text):
    """
    Returns (year, season_value) for picking the 'latest' period.
      - year is int from e.g. "2025"
      - season_value is 1 if 'Autumn' in text, else 0 (for 'Spring').
    """
    if not period_text:
        return (0, -1)

    year_match = re.search(r'20\d{2}', period_text)
    year = int(year_match.group(0)) if year_match else 0
    season_value = 1 if 'Autumn' in period_text else 0
    return (year, season_value)

def extract_last_modified(soup):
    """
    Finds 'Last modified' label anywhere in the page, returning
    the adjacent <time> text if present. Otherwise, empty string.
    """
    label = soup.find('div', class_='label', string=re.compile(r'Last modified', re.IGNORECASE))
    if not label:
        return ""
    time_el = label.find_next('time')
    return get_text_or_none(time_el)

def get_section_text(soup, section_id):
    """
    Finds <h2 id=section_id>, returns text in the next sibling <div>.
    Used for "about" content.
    """
    heading_tag = soup.find('h2', id=section_id)
    if not heading_tag:
        return ""
    next_div = heading_tag.find_next_sibling('div')
    if next_div:
        return next_div.get_text("\n", strip=True)
    return ""

def parse_prereq_and_selection(soup):
    """
    1) Locate <h2 id='prerequisites-and-selection'>.
    2) Gather all subsequent siblings (until next <h2>).
    3) Within those siblings, parse:
       - <h3> entry requirements
       - <h3> selection
    """
    result = {
        "entry_requirements": "",
        "selection": ""
    }

    # Find the main <h2> with id='prerequisites-and-selection'
    prereq_heading = soup.find('h2', id='prerequisites-and-selection')
    if not prereq_heading:
        return result  # not found, so empty strings

    # Collect all siblings after this <h2>, until we hit the next <h2>
    # or run out of siblings.
    collected_siblings = []
    for sibling in prereq_heading.next_siblings:
        # A new <h2>, stop because we've hit the next major section.
        if sibling.name == 'h2':
            break
        collected_siblings.append(sibling)

    def capture_text_for_subheading(target_subheading):
        """
        In 'collected_siblings', find the h3 that matches target_subheading,
        then gather all textual siblings until the next h2/h3.
        """
        text_fragments = []
        is_capturing = False

        for s in collected_siblings:
            # If it's an <h3> tag, check if it matches our target subheading
            if s.name == 'h3' and target_subheading.lower() in get_text_or_none(s).lower():
                # Start capturing after we see the subheading
                is_capturing = True
                continue

            # If we run into another heading (h2 or h3) while capturing, stop
            if s.name in ('h2', 'h3') and is_capturing:
                break

            # If capturing, gather text from this sibling
            if is_capturing:
                text_fragments.append(get_text_or_none(s))

        # Join everything with some spacing
        return "\n".join(filter(None, text_fragments))

    # Parse 'Entry requirements'
    entry_req_text = capture_text_for_subheading('Entry requirements')
    # Parse 'Selection'
    selection_text = capture_text_for_subheading('Selection')

    result["entry_requirements"] = entry_req_text
    result["selection"] = selection_text

    return result

def extract_course_info(html_content, url):
    soup = BeautifulSoup(html_content, 'html.parser')

    last_modified = extract_last_modified(soup)
    course_code = extract_course_code(url)

    # Course name from <meta property="og:title">
    course_name_meta = soup.find('meta', property='og:title')
    course_name = course_name_meta['content'] if course_name_meta else ""

    # Language switcher
    lang_switcher = soup.find('div', class_='language-switcher')
    svenska_path, international_path = None, None
    if lang_switcher:
        svenska_link = lang_switcher.find('a', hreflang='sv')
        international_link = lang_switcher.find('a', hreflang='en')
        svenska_path = svenska_link.get('href') if svenska_link else None
        international_path = international_link.get('href') if international_link else None

    about_text = get_section_text(soup, 'about')
    # Parse prereqs + selection
    prereq_sel_dict = parse_prereq_and_selection(soup)

    # Find all period sections
    period_sections = soup.find_all('div', class_='education-offering-accordion')
    latest_period_data = None
    latest_year = 0
    latest_season = -1

    for section in period_sections:
        period_heading = section.find('h2', class_='heading-component')
        if not period_heading:
            continue

        period = get_text_or_none(period_heading)
        year, season = parse_period_value(period)

        # Keep only the "latest" period
        if (year > latest_year) or (year == latest_year and season > latest_season):
            latest_year = year
            latest_season = season

            # Gather metadata
            meta_items = section.find_all('div', class_='meta')
            metadata = {}

            for meta in meta_items:
                label_div = meta.find('div', class_='label')
                if not label_div:
                    continue

                label_text = get_text_or_none(label_div).lower()
                data_div = meta.find('div', class_='meta__data')

                if label_text in ['duration', 'application period']:
                    if data_div:
                        times = data_div.find_all('time')
                        if len(times) == 2:
                            metadata[f"{label_text}_start"] = get_text_or_none(times[0])
                            metadata[f"{label_text}_end"] = get_text_or_none(times[1])
                else:
                    if data_div:
                        div_text = data_div.find('div')
                        metadata[label_text] = (
                            get_text_or_none(div_text) if div_text else get_text_or_none(data_div)
                        )

            tuition_info = {
                "full_education_cost": "",
                "first_payment": "",
                "fee_info": "No fees are charged for EU and EEA citizens, Swedish residence permit holders and exchange students.",
                "tuition_link": "https://www.gu.se/en/study-in-gothenburg/apply/tuition-fees"
            }

            tuition_label_div = section.find(
                'div',
                class_='label',
                string=re.compile(r'Tuition', re.IGNORECASE)
            )
            if tuition_label_div:
                tuition_meta_wrapper = tuition_label_div.parent
                cost_divs = tuition_meta_wrapper.find_all('div', class_='meta__data')
                for cost_div in cost_divs:
                    cost_text = get_text_or_none(cost_div)
                    lower_text = cost_text.lower()

                    if 'full education cost:' in lower_text:
                        splitted = cost_text.split(':', 1)
                        if len(splitted) > 1:
                            tuition_info["full_education_cost"] = splitted[1].strip()
                        else:
                            tuition_info["full_education_cost"] = cost_text

                    elif 'first payment:' in lower_text:
                        splitted = cost_text.split(':', 1)
                        if len(splitted) > 1:
                            tuition_info["first_payment"] = splitted[1].strip()
                        else:
                            tuition_info["first_payment"] = cost_text

            # Create final dict for the newest period
            latest_period_data = {
                "course_code": course_code,
                "website": {
                    "svenska": svenska_path or "",
                    "international_website": international_path or "",
                    "course_name": course_name,
                    "period": period,
                    "study_pace": metadata.get("study pace", ""),
                    "time": metadata.get("time", ""),
                    "location": metadata.get("location", ""),
                    "study_form": metadata.get("study form", ""),
                    "language": metadata.get("language", ""),
                    "duration_start": metadata.get("duration_start", ""),
                    "duration_end": metadata.get("duration_end", ""),
                    "application_period_start": metadata.get("application period_start", ""),
                    "application_period_end": metadata.get("application period_end", ""),
                    "application_code": metadata.get("application code", ""),
                    "syllabus": f"https://kursplaner.gu.se/pdf/kurs/en/{course_code}",
                    "tuition": tuition_info,
                    "about": about_text,
                    "prerequisites_and_selection": {
                        "entry_requirements": prereq_sel_dict["entry_requirements"],
                        "selection": prereq_sel_dict["selection"]
                    },
                    "last_modified": last_modified
                }
            }

    return [latest_period_data] if latest_period_data else []

def main():
    urls = get_urls()
    all_courses = []

    for i, url in enumerate(urls, 1):
        print(f"Processing {i}/{len(urls)}: {url}")
        try:
            response = requests.get(url)
            response.raise_for_status()
            
            course_data_list = extract_course_info(response.text, url)
            all_courses.extend(course_data_list)

            # Delay between requests
            time.sleep(2)

        except Exception as e:
            print(f"Error processing {url}: {str(e)}")

    with open('website.json', 'w', encoding='utf-8') as f:
        json.dump(all_courses, f, ensure_ascii=False, indent=2)

    print(f"\nProcessed {len(all_courses)} courses. Data saved to website.json")

if __name__ == "__main__":
    main()
