from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from PIL import Image
from datetime import datetime
import requests
import os

def download_image(image_url, save_path):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    save_path_with_timestamp = os.path.splitext(save_path)[0] + '_' + timestamp + os.path.splitext(save_path)[1]

    try:
        response = requests.get(image_url)
        response.raise_for_status()  # This will raise an HTTPError for bad responses
        with open(save_path_with_timestamp, 'wb') as f:
            f.write(response.content)
        print(f"Captcha image saved to {save_path_with_timestamp}")
        return save_path_with_timestamp
    except Exception as e:
        print(f"Failed to download the image: {e}")
        return None

def solve_captcha(captcha_path):
    try:
        image = Image.open(captcha_path).convert("RGB")
        processor = TrOCRProcessor.from_pretrained('microsoft/trocr-base-printed')
        model = VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-base-printed')
        pixel_values = processor(images=image, return_tensors="pt").pixel_values

        generated_ids = model.generate(pixel_values)
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        print(f"Solved CAPTCHA: {generated_text}")
        return generated_text
    except Exception as e:
        print(f"An error occurred while solving CAPTCHA: {e}")
        return None

def parse_buybox_info(info):
    def extract_price(text):
        parts = text.split("\n")
        if len(parts) > 1 and "€" in parts[1]:
            return parts[0].replace("\u202f", "").strip() + "." + parts[1].replace("€", "").strip()
        return None

    def parse_delivery_option(text):
        delivery_type = "Gratuite" if "GRATUITE" in text.upper() else "Accélérée" if "accélérée" in text else "Standard"
        # Extracting date more accurately
        parts = text.split(" ")
        date_idx = -1
        for idx, part in enumerate(parts):
            if part.lower() in ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]:
                date_idx = idx
                break
        eta = " ".join(parts[date_idx-1:date_idx+1]) if date_idx != -1 else "Date not found"
        return {"type": delivery_type, "ETA": eta}

    def get_condition(text):
        if "Neuf :" in text:
            return "Neuf"
        elif "D’occasion" in text:
            return text.split(" – ")[1]
        return None

    products = {}
    current_condition = None
    next_is_ship_from = False
    next_is_stock_by = False

    for item in info:
        text = item['text'].replace("\u202f", "").strip()

        if next_is_ship_from:
            products[current_condition]["ship_from"] = text
            next_is_ship_from = False
            continue

        if next_is_stock_by:
            products[current_condition]["stock_by"] = text
            next_is_stock_by = False
            continue

        condition = get_condition(text)
        if condition:
            current_condition = condition
            if condition not in products:
                products[condition] = {
                    "condition": condition,
                    "delivery_option": [],
                    "stock_status": "NOT PARSED"
                }

        price = extract_price(text)
        if price and "price" not in products[current_condition]:
            products[current_condition]["price"] = price

        if "Retours GRATUITS" in text:
            products[current_condition]["return_policy"] = "Retours GRATUITS"
        elif "Livraison" in text:
            delivery_option = parse_delivery_option(text)
            products[current_condition]["delivery_option"].append(delivery_option)
        elif "Expédié" in text:
            next_is_ship_from = True
        elif "Vendu par" in text:
            next_is_stock_by = True
        elif "En stock" in text:
            products[current_condition]["stock_status"] = "En stock"

    return [value for key, value in products.items()]




options = Options()
options.headless = True
options.add_argument("window-size=1200x600")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3")

driver = webdriver.Chrome(options=options)

try:
    driver.get("https://www.amazon.fr/dp/B0CHWWM3JH")
    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

    captcha_message = driver.find_elements(By.XPATH, "//*[contains(text(), 'Enter the characters you see below')]")

    if captcha_message:
        print("CAPTCHA detected")

        captcha_image = driver.find_element(By.XPATH, "//img[contains(@src, 'captcha')]")
        image_url = captcha_image.get_attribute('src')
        save_path = os.path.join(os.getcwd(), 'captcha_image.png')
        captcha_image_path = download_image(image_url, save_path)

        if captcha_image_path:
            solved_captcha = solve_captcha(captcha_image_path)

            if solved_captcha:
                input_field = driver.find_element(By.ID, "captchacharacters")  # You might need to adjust this ID based on the actual page structure
                input_field.send_keys(solved_captcha)

                # Submit the form here. You might need to adjust this based on the actual page structure.
                # For example, you can click the submit button or simulate pressing Enter.

    else:
        print("No CAPTCHA detected.")
        buybox = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.ID, 'buybox'))  # This is an example; the actual ID/class should be determined
        )

        # Find all child elements within the buybox. This is a broad approach; refine the selector as needed.
        span_elements_with_text = [element for element in buybox.find_elements(By.TAG_NAME, "span") if element.text.strip()]


        # Initialize a table to store CSS selectors and their values
        info = []

        for element in span_elements_with_text:
            # Get the text content of the span element
            text_content = element.text.strip()

            # Get additional attributes to help infer the name
            element_classes = element.get_attribute("class").strip().replace(" ", ".")
            element_tag = element.tag_name
            element_id = element.get_attribute("id").strip()

            # Formulate a generic name using tag, class, and ID
            generic_name_parts = [part for part in [element_tag, element_classes, element_id] if part]
            generic_name = ">".join(generic_name_parts)

            # Construct a dictionary to hold the element's information
            element_info = {
                "name": generic_name or "UnnamedElement",
                "text": text_content
            }

            # Add to the list
            info.append(element_info)

        # Print the collected information
        parsed_info = parse_buybox_info(info)
        print(parsed_info)

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    driver.quit()
