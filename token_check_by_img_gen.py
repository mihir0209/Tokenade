import requests
import base64
import uuid

# Constants
ENDPOINT = "https://aisandbox-pa.googleapis.com/v1/whisk:generateImage"
WORKFLOW_ID = "f6348ffc-4d9c-4091-ad46-028ba6de03b9"
SESSION_ID = str(uuid.uuid4())
IMAGE_MODEL = "IMAGEN_3_5"
ASPECT_RATIO = "IMAGE_ASPECT_RATIO_LANDSCAPE" # Other options include IMAGE_ASPECT_RATIO_PORTRAIT, IMAGE_ASPECT_RATIO_SQUARE
MEDIA_CATEGORY = "MEDIA_CATEGORY_BOARD"
SEED = 897320  # Can randomize or modify if needed

def generate_image(prompt):
    payload = {
        "clientContext": {
            "workflowId": WORKFLOW_ID,
            "tool": "BACKBONE",
            "sessionId": SESSION_ID
        },
        "imageModelSettings": {
            "imageModel": IMAGE_MODEL,
            "aspectRatio": ASPECT_RATIO
        },
        "seed": SEED,
        "prompt": prompt,
        "mediaCategory": MEDIA_CATEGORY
    }

    headers = {
    "Authorization": "Bearer ya29.a0ATi6K2tTp0t7i72XlH4uBItb7CiIXb8SKUSZW-dynkmnEnA4OWCN642IAFCiG4h_9xXk64W74e6h4gN2wtHUBf9_A-IaDeAMzKNgCFxAXotQOEWvnrxvQsdrkqTIbpBOflzNP22OaNs8_j10RcsJ-EeHAjL-Afx-KMwayQHpw1ykQadGMeQnoL_HgtKqmyRpLY8kxhori2oSeuH7O17G21_D32xaQweXGXlSDl41u0AHIYviarZjliRYucjLQV3DGnjnXe--UyanTyPoC4pu4Tty7J2WWjIXz6TCaLWax9CKy-nZKClwt2fyQ31J3p6HPFMx402U9zzVHJfxbblT5VMB__mO5zVgwUJxosAxGAaCgYKAUcSARISFQHGX2Mi97smQ5riumY38R0tBWcLsA0369",
    "Content-Type": "application/json"
}


    response = requests.post(ENDPOINT, json=payload, headers=headers)

    if response.status_code == 200:
        data = response.json()
        image_data = data['imagePanels'][0]['generatedImages'][0]['encodedImage']
        image_bytes = base64.b64decode(image_data)

        file_name = "generated_image.jpg"
        with open(file_name, "wb") as f:
            f.write(image_bytes)

        print(f"✅ Image saved as {file_name}")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")

# Prompt input
user_prompt = input("Enter your image prompt: ")
generate_image(user_prompt)
