import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timezone
import re

result_data = []

def split_outside_parentheses(s, delimiter=','):
    """Split string by delimiter, ignoring delimiters inside parentheses."""
    parts = []
    current = []
    depth = 0
    for c in s:
        if c == '(':
            depth += 1
        elif c == ')':
            if depth > 0:
                depth -= 1
        if c == delimiter and depth == 0:
            part = ''.join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(c)
    part = ''.join(current).strip()
    if part:
        parts.append(part)
    return parts

def clean_subingredient(name):
    """Clean and normalize sub-ingredient name."""
    # Lowercase
    name = name.strip().lower()
    # Replace non-breaking hyphen or similar chars with normal hyphen or space
    name = re.sub(r'[\u2011\u2010\u2013\u2014]', '-', name)
    # Remove content inside parentheses but keep the outer word (e.g. "syltet agurk (agurk, vann)" -> "syltet agurk")
    name = name.split('(')[0].strip().rstrip(')')
    # Replace multiple spaces with single space
    name = re.sub(r'\s+', ' ', name)
    return name

def parse_ingredients(raw_str):
    # Preprocess: remove trailing periods and normalize whitespace
    raw_str = raw_str.strip()
    raw_str = re.sub(r'\s+', ' ', raw_str)

    # Pattern to extract groups with percent and their sub-ingredients:
    # Group name may have spaces and hyphens, percent is inside parentheses with optional decimal and % sign after
    # Format: GROUP_NAME (PERCENT %): sub-ingredients.....
    # We use a regex to capture group name, percent, and sub-ingredients until next group or end
    pattern = re.compile(
        r'([A-ZÆØÅ\s\-]+)\s*\(([\d,\.]+)\s?%\):\s*(.*?)(?=(?:[A-ZÆØÅ\s\-]+\s*\([\d,\.]+%\):)|$)', re.DOTALL)
    matches = pattern.findall(raw_str)
    result = []

    for group, percent_str, subs_str in matches:
        group = group.strip()
        # Replace comma decimal by dot and convert percent to float
        percent = float(percent_str.replace(',', '.'))

        # Clean sub-ingredients:
        # First, split by commas and ' og '
        sub_parts = split_outside_parentheses(subs_str.rstrip('.'))

        cleaned_subs = []
        for sub in sub_parts:
            clean_name = clean_subingredient(sub)
            if clean_name and clean_name not in cleaned_subs:
                cleaned_subs.append(clean_name)
        result.append({
            "group": group,
            "percent": percent,
            "sub": cleaned_subs
        })
    return result

def get_product_list(search_url):
    try:
        # Fetch page with headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        results_list = soup.find('div', class_='k-grid k-grid--row-gap-spacing-4')  # Get main container

        # Extract all product links from div.row elements
        product_links = []
        for row in results_list.find_all('article'):
            for product in row.find_all('a', href=True):  # Find all <a> tags with href
                product_link = f"https://oda.com{product['href']}"
                product_links.append(product_link)

        print(f"Found {len(product_links)} product links:")

        # Save to file
        with open('product_links.txt', 'w', encoding="utf-8") as f:
            f.write('\n'.join(product_links))

        return product_links

    except Exception as e:
        print(f"Error: {e}")

def get_product_detail(product_url):
    try:
        # Fetch page with headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(product_url, headers=headers)
        response.raise_for_status()

        # Assuming 'html' contains your HTML content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Initialize a dictionary to store product information
        product_info = {
            'source': 'Oda',
            'product_id': None,
            'producer': None,
            'brand': None,
            'title': None,
            'ingredients': [],
            'allergens': [],
            'nutrition': {"per_100g": {}},
            'package_size': {},
            'origin_country': None,
            'gtin': None,
            'epd': None,
            'labels': [],
            'source_url': product_url,
            'last_updated': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),

            'product_description': None,
            'image': None,
        }

        # Extract product id
        match = re.search(r'/products/(\d+)', product_url)
        product_info['product_id'] = match.group(1) if match else None

        # Extract product title and brand
        product_info_section = soup.find('div', attrs={'data-testid': 'product-info-section'})
        title = product_info_section.find('h1').get_text(strip=True) if product_info_section else None
        sub_titles = product_info_section.find('p').get_text(strip=True).split(', ')

        product_info['title'] = title + ' - ' + ' - '.join(sub_titles[:-1])
        product_info['brand'] = sub_titles[-1].strip()
        
        # Extract product image url
        product_image = soup.find('main', id="main-content").find('img', class_='k-image k-image--contain')
        product_info['image'] = product_image['src'] if product_image else None

        # Extract product details
        nutrition_map = {
            "Fett": "fat_g",
            "hvorav mettede fettsyrer": "saturated_fat_g",
            "Karbohydrater": "carbs_g",
            "hvorav sukkerarter": "sugars_g",
            "Protein": "protein_g",
            "Salt": "salt_g",
        }
        product_details = soup.find_all('div', class_='k-grid k-pt-3 k-pb-6')
        for detail in product_details:
            items = detail.find_all('div')
            key = items[0].get_text(strip=True)
            value = items[1].get_text(strip=True)

            # Check if this item indicates nutrition
            if key == "Energi":
                clean_val = re.sub(r"(\d)\s+(\d)", r"\1\2", value) # Remove spaces inside numbers (e.g., "1 020" → "1020")
                values = re.findall(r"\d+", clean_val)
                product_info['nutrition']['per_100g']['energy_kJ'] = int(values[0])
                product_info['nutrition']['per_100g']['energy_kcal'] = int(values[1])
                continue
            if key in nutrition_map:
                value = float(re.search(r"\d+\.\d+", value).group())
                product_info['nutrition']['per_100g'][nutrition_map[key]] = value
                continue
                
            # In case of other contents
            if key == "Leverandør":
                product_info['producer'] = value
                continue
            if key == "Allergener":
                product_info['allergens'] = value.rstrip('.').split(', ')
                continue
            if key == "Ingredienser":
                product_info['ingredients'] = parse_ingredients(value)

        # Save result data
        global result_data
        result_data.append(product_info)

    except Exception as e:
        print(f"Error: {e}")

def oda_scraper():
    # Initiate the result data
    global result_data
    result_data = []

    search_url = "https://oda.com/no/search/products/?q=lunch"
    product_list = get_product_list(search_url)

    for product_url in product_list:
        get_product_detail(product_url)

    with open("product_info.json", 'w', encoding="utf-8") as file:
        json.dump(result_data, file, ensure_ascii=False, indent=2)

    return result_data

if __name__ == "__main__":
    oda_scraper()