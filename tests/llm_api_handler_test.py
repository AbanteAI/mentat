import base64
from io import BytesIO

from PIL import Image

from mentat.llm_api_handler import prompt_tokens


def test_prompt_tokens():
    messages = [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help you today?"},
    ]
    model = "gpt-4-vision-preview"

    assert prompt_tokens(messages, model) == 24

    # An image that must be scaled twice and then fits in 6 512x512 panels
    img = Image.new("RGB", (768 * 4, 1050 * 4), color="red")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    image_url = f"data:image/png;base64,{img_base64}"

    messages.append(
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": image_url}}],
        }
    )

    assert prompt_tokens(messages, model) == 24 + 6 * 170 + 85 + 5
