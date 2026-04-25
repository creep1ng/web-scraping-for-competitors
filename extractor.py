import os
from typing import List
from bs4 import BeautifulSoup
from openai import OpenAI


SYSTEM_PROMPT = """Eres un extractor de datos de productos de e-commerce. Tu tarea es analizar el HTML de una página web y extraer la información del producto.

Devuelve EXACTAMENTE un objeto JSON con esta estructura (sin texto adicional):
{
    "nombre_pagina": "nombre del sitio",
    "link": "URL original",
    "nombre_producto": "nombre del producto encontrado",
    "precio": "precio del producto"
}

Si no encuentras un producto o la página no es un e-commerce válido, devuelve:
{
    "nombre_pagina": "desconocido",
    "link": "",
    "nombre_producto": "",
    "precio": ""
}
"""


def clean_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    body = soup.find("body")
    if body:
        return str(body)

    return str(soup)


def extract_markdown(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text_parts = []
    for element in soup.body.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "span", "div", "li", "a"]):
        text = element.get_text(strip=True)
        if text and len(text) > 2:
            text_parts.append(text)

    return "\n".join(text_parts[:100])


def extract_product_info(html_content: str, url: str) -> dict:
    cleaned_html = clean_html(html_content)

    client = OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )

    model = os.getenv("LLM_MODEL", "stepfun/step-3.5-flash")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"URL: {url}\n\nHTML:\n{cleaned_html[:15000]}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    result = response.choices[0].message.content
    if result:
        import json
        return json.loads(result)

    return {
        "nombre_pagina": "error",
        "link": url,
        "nombre_producto": "",
        "precio": ""
    }


async def extract_product_info_async(html_content: str, url: str) -> dict:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, extract_product_info, html_content, url)
