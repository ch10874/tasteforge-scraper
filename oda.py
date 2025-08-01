import requests
from bs4 import BeautifulSoup
import openai
import json
from datetime import datetime, timezone
import os
import re
from dotenv import load_dotenv

load_dotenv()

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    # Remove content in parentheses but keep the main name, e.g.:
    # "sylteagurk (agurk, vann, eddik, salt)" -> "sylteagurk"
    # Also fix typos like 'storfe‑collagen' -> 'storfe collagen'
    name = name.strip()
    # Replace non-breaking hyphen or similar chars with space
    name = re.sub(r'[\u2011\u2010\u2013\u2014\-]+', ' ', name)
    # Remove text within parentheses
    name = name.split('(')[0].strip().rstrip(')')
    # lowercase
    name = name.lower()
    # Replace multiple spaces with single space
    name = re.sub(r'\s+', ' ', name)
    return name

def parse_ingredients(raw_str):
    raw_str = raw_str.strip().rstrip('.') # Remove trailing period if present
    # Pattern to match: GROUP_NAME PERCENT % ( ... )
    pattern = re.compile(r'([A-ZÆØÅ\s]+?)\s*(\d+)\s*%\s*\((.*?)\)(?=, [A-ZÆØÅ\s]+ \d+ %|$)', re.DOTALL)
    matches = pattern.findall(raw_str)
    result = []

    for group, percent, subs_str in matches:
        group = group.strip()
        percent = int(percent)
        # Split sub-ingredients by commas outside parentheses
        subs = split_outside_parentheses(subs_str)
        cleaned_subs = []
        for sub in subs:
            # Clean subingredient
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

        #Extract product id
        match = re.search(r'/products/(\d+)', product_url)
        product_info['product_id'] = match.group(1) if match else None
        print(product_info)
        return

        # Extract brand and producer info
        brand_info = soup.find('div', class_='brands')
        if brand_info:
            for p in brand_info.find_all('p'):
                text = p.get_text(strip=True)
                if 'PRODUSENT:' in text:
                    product_info['producer'] = text.split(':')[-1].strip()
                elif 'VAREMERKE:' in text:
                    product_info['brand'] = text.split(':')[-1].strip()

        # Extract product title
        product_info['title'] = soup.find('h1').get_text(strip=True) if soup.find('h1') else None

        # Extract ingredients
        ingredients_section = soup.find('section', class_='ingredients')
        if ingredients_section:
            ingredients_text = ingredients_section.find('p').get_text(strip=True)
            ingredients_json = parse_ingredients(ingredients_text)
            product_info['ingredients'] = ingredients_json

        # Extract allergens
        allergens_section = soup.find('section', class_='allergens')
        for row in allergens_section.find('tbody').find_all('tr'):
            allergen_name = row.find('td').get_text(strip=True)
            if 'circle-red' in str(row):
                product_info['allergens'].append(allergen_name)

        # Extract nutrition information
        nutrition_map = {
            "Energi": "energy",
            "Fett": "fat_g",
            "- Mettede fettsyrer": "saturated_fat_g",
            "Karbohydrat": "carbs_g",
            "- Sukkerarter": "sugars_g",
            "Protein": "protein_g",
            "Salt": "salt_g",
        }
        nutrition_section = soup.find('h2', string='Næringsinnhold')
        if nutrition_section:
            nutrition_table = nutrition_section.find_next('table', class_='div-table')
            if nutrition_table:
                for row in nutrition_table.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) == 2:
                        nutrient = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        if nutrient == "Energi":
                            clean_val = re.sub(r"(\d)\s+(\d)", r"\1\2", value) # Remove spaces inside numbers (e.g., "1 020" → "1020")
                            values = re.findall(r"\d+", clean_val)
                            product_info['nutrition']['per_100g']['energy_kJ'] = int(values[0])
                            product_info['nutrition']['per_100g']['energy_kcal'] = int(values[1])
                        else:
                            value_str = re.search(r"\d+\.\d+", value.replace(",", ".")).group()
                            value_num = float(value_str) if "." in value_str else int(value_str)
                            product_info['nutrition']['per_100g'][nutrition_map[nutrient]] = value_num

        # Extract product details
        details_section = soup.find('h2', string='Produktinformasjon')
        if details_section:
            details_table = details_section.find_next('table', id='product-info')
            if details_table:
                for row in details_table.find_all('tr'):
                    cells = row.find_all('td')
                    if cells[0].get_text(strip=True) == 'Opphavsland':
                        product_info['origin_country'] = cells[1].get_text(strip=True)
                    elif cells[0].get_text(strip=True) == 'GTIN':
                        product_info['gtin'] = cells[1].get_text(strip=True)
                    elif cells[0].get_text(strip=True) == 'EPD-nummer':
                        product_info['epd'] = cells[1].get_text(strip=True)

        # Extract description (if available)
        description = soup.find('div', class_='col-sm-9').find('p', class_='paragraph-padding')
        product_info['product_description'] = description.get_text(strip=True) if description else None

        # Extract product image url
        image_section = soup.find('div', class_='image-header')
        product_info['image'] = image_section.find('img')['src'] if image_section and image_section.find('img') else None

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
    # product_list = get_product_list(search_url)

    # for product_url in product_list:
    get_product_detail("https://oda.com/no/products/66066-norgescatering-baguette-med-ost-skinke/")

    # with open("product_info.json", 'w', encoding="utf-8") as file:
    #     json.dump(result_data, file, ensure_ascii=False, indent=2)

    # return result_data

if __name__ == "__main__":
    oda_scraper()