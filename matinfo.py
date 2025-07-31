import requests
from bs4 import BeautifulSoup
import openai
import json
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

load_dotenv()

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

result_data = []

def get_ingredients(raw_string):
    prompt = """I have a raw ingredients string describing groups of ingredients with their percentage amounts and nested sub-ingredients. The format typically looks like this:

"GROUP_NAME PERCENT % (sub-ingredient1, sub-ingredient2, sub-ingredient3 (nested sub-ingredients), ...), NEXT_GROUP PERCENT % (...), ..."

Your task is to parse this string and output structured JSON data as an array of objects. Each object should contain:

- "group": The name of the ingredient group (text before the percentage sign).

- "percent": The numeric percentage value associated with that group.

- "sub": An array of the immediate sub-ingredients within the parentheses of that group. For complex nested ingredients (sub-ingredients that have their own parentheses), include only the main sub-ingredient names without all nested details or parentheses content, i.e., treat nested ingredients as a single sub-ingredient name without inner breakdown, unless clearly separated by commas outside parentheses.

Normalize all sub-ingredient names by:

- Making them lowercase.

- Removing extra parentheses details inside nested sub-ingredients (except treat the entire nested phrase as one sub-ingredient).

- Removing duplicate entries when possible.

- Replacing special characters or typos for clarity (for instance, change “storfe‑collagen” to “storfe collagen").

Return only valid JSON content without any description or any other contents."""

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": raw_string}
        ],
        temperature=0.0,  # Controls randomness (0.0 = deterministic, 1.0 = creative)
    )

    json_data = json.loads(response.choices[0].message.content)
    return json_data

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
        results_list = soup.find(id="results-list")  # Get main container

        # Extract all product links from div.row elements
        product_links = []
        for row in results_list.find_all('div', class_='row'):
            for product in row.find_all('a', href=True):  # Find all <a> tags with href
                product_links.append(product['href'])

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
            'source': 'Matinfo',
            'product_id': None,
            'producer': None,
            'brand': None,
            'title': None,
            'ingredients': [],
            'allergens': [],
            'nutrition': {},
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
        product_numbers = soup.find('div', class_='product-numbers').get_text() if soup.find('div', class_='product-numbers') else None
        product_info['product_id'] = product_numbers.split("GTIN:")[1].strip()

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
            ingredients_json = get_ingredients(ingredients_text)
            product_info['ingredients'] = ingredients_json

        # Extract allergens
        allergens_section = soup.find('section', class_='allergens')
        for row in allergens_section.find('tbody').find_all('tr'):
            allergen_name = row.find('td').get_text(strip=True)
            if 'circle-red' in str(row):
                product_info['allergens'].append(allergen_name)

        # Extract nutrition information
        nutrition_section = soup.find('h2', string='Næringsinnhold')
        if nutrition_section:
            unit_amount = nutrition_section.find_next('p').get_text(strip=True)
            product_info['nutrition']['unit'] = unit_amount
            nutrition_table = nutrition_section.find_next('table', class_='div-table')
            if nutrition_table:
                for row in nutrition_table.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) == 2:
                        nutrient = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        product_info['nutrition'][nutrient] = value

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

        with open("product_info.json", 'w', encoding="utf-8") as file:
            json.dump(result_data, file, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"Error: {e}")

def matinfo_scraper():
    # Initiate the result data
    global result_data
    result_data = []

    search_url = "https://produkter.matinfo.no/resultat?query=nordic%20lunch"
    product_list = get_product_list(search_url)

    for product_url in product_list[:2]:
        get_product_detail(product_url)

    return result_data

if __name__ == "__main__":
    matinfo_scraper()