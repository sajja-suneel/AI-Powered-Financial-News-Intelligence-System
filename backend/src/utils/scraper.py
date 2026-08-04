# src/utils/scraper.py
import sys
import asyncio
import os
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode
from urllib.parse import urljoin, urlparse  # <-- Added for relative link parsing
from src.utils.logger import get_logger

logger = get_logger("utils.scraper")

class WebScraper:
    """
    A class-based utility that handles thread-isolated web scraping using Crawl4AI
    and Playwright, saving structured resources to disk caches.
    """

    @staticmethod
    def slugify_url(url: str) -> str:
        """
        Transforms URL into a clean alphanumeric string for filenames.
        """
        import re
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_")
        netloc = parsed.netloc.replace(".", "_")
        filename = f"{netloc}_{path}" if path else netloc
        filename = re.sub(r'[^\w\-]', '_', filename)
        return filename[:100]

    @staticmethod
    async def run_enterprise_scrape_async(url: str) -> dict:
        """
        Runs the full Playwright enterprise scraping flow, downloads resources, 
        and extracts JS charts, canvas info, tables, PDFs, and network captures.
        """
        from playwright.async_api import async_playwright
        import requests
        
        # Create output directories
        output_dirs = {
            "pages": "output/pages",
            "tables": "output/tables",
            "images": "output/images",
            "pdfs": "output/pdfs",
            "charts": "output/charts",
            "network": "output/network",
            "metadata": "output/metadata"
        }
        for d in output_dirs.values():
            os.makedirs(d, exist_ok=True)
            
        slug = WebScraper.slugify_url(url)
        logger.info(f"[ENTERPRISE SCRAPER] Initializing run for url: {url} (slug: {slug})")
        
        network_logs = []
        js_charts = []
        canvas_charts = []
        svg_charts = []
        embedded_docs = []
        metadata = {}
        links = {"internal": [], "external": [], "email": [], "tel": []}
        
        html_content = ""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-http2"]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    timezone_id="Asia/Kolkata"
                )
                await context.set_extra_http_headers({
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "accept-language": "en-US,en;q=0.9",
                    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1"
                })
                page = await context.new_page()
                # Stealth Evasion: Hide webdriver flag
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                # Setup response network interceptor
                async def handle_response(response):
                    try:
                        content_type = response.headers.get("content-type", "")
                        if "json" in content_type or response.request.resource_type in ["fetch", "xhr"]:
                            text_val = await response.text()
                            try:
                                json_val = json.loads(text_val)
                            except Exception:
                                json_val = text_val
                            network_logs.append({
                                "url": response.url,
                                "method": response.request.method,
                                "status": response.status,
                                "response_json": json_val,
                                "headers": dict(response.headers)
                            })
                    except Exception:
                        pass
                page.on("response", lambda res: asyncio.create_task(handle_response(res)))
                
                # Navigate to the target url
                try:
                    await page.goto(url, wait_until="networkidle", timeout=50000)
                except Exception as e:
                    logger.warning(f"Timeout waiting for networkidle, trying load state: {e}")
                    try:
                        await page.goto(url, wait_until="load", timeout=30000)
                    except Exception as e2:
                        logger.error(f"Navigation failed: {e2}")
                        await browser.close()
                        raise e2

                # Extract basic data
                html_content = await page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                title = soup.title.string.strip() if soup.title else "Scraped Document"
                
                # Extract JS Chart Data, Canvas element, SVG, links, and embedded docs using client evaluation
                eval_js = """
                (() => {
                    const data = {
                        canvas_charts: [],
                        js_charts: [],
                        svg_charts: [],
                        embedded_docs: [],
                        metadata: {},
                        links: { internal: [], external: [], email: [], tel: [] }
                    };

                    // Canvas Detection
                    document.querySelectorAll("canvas").forEach((canvas, idx) => {
                        data.canvas_charts.push({
                            index: idx,
                            id: canvas.id || "",
                            className: canvas.className || "",
                            width: canvas.width,
                            height: canvas.height
                        });
                    });

                    // JS Charts
                    if (window.Highcharts && Array.isArray(window.Highcharts.charts)) {
                        window.Highcharts.charts.forEach((chart, idx) => {
                            if (chart) {
                                data.js_charts.push({
                                    type: "Highcharts",
                                    index: idx,
                                    title: chart.title ? chart.title.textStr : "",
                                    options: chart.userOptions || {}
                                });
                            }
                        });
                    }
                    if (window.Chart && window.Chart.instances) {
                        Object.keys(window.Chart.instances).forEach((key) => {
                            const chart = window.Chart.instances[key];
                            if (chart) {
                                data.js_charts.push({
                                    type: "Chart.js",
                                    id: key,
                                    config: chart.config ? chart.config._config : {}
                                });
                            }
                        });
                    } else if (window.Chart) {
                        document.querySelectorAll("canvas").forEach((canvas, idx) => {
                            try {
                                const chart = window.Chart.getChart(canvas);
                                if (chart) {
                                    data.js_charts.push({
                                        type: "Chart.js",
                                        index: idx,
                                        config: chart.config ? chart.config._config : {}
                                    });
                                }
                            } catch(e) {}
                        });
                    }
                    if (window.ApexCharts) {
                        data.js_charts.push({ type: "ApexCharts", detected: true });
                    }
                    if (window.echarts) {
                        data.js_charts.push({ type: "ECharts", detected: true });
                    }
                    if (window.TradingView || document.querySelector("iframe[src*='tradingview']")) {
                        data.js_charts.push({ type: "TradingView", detected: true });
                    }

                    // SVG Source
                    document.querySelectorAll("svg").forEach((svg, idx) => {
                        data.svg_charts.push({
                            index: idx,
                            id: svg.id || "",
                            className: svg.className ? (svg.className.baseVal || "") : "",
                            outerHTML: svg.outerHTML
                        });
                    });

                    // Embedded docs
                    document.querySelectorAll("iframe, embed, object").forEach((el, idx) => {
                        data.embedded_docs.push({
                            tag: el.tagName.toLowerCase(),
                            src: el.src || el.data || "",
                            type: el.type || ""
                        });
                    });

                    // Metadata Extraction
                    const getMeta = (name) => {
                        const el = document.querySelector(`meta[name='${name}'], meta[property='${name}']`);
                        return el ? el.getAttribute("content") : "";
                    };
                    data.metadata = {
                        title: document.title,
                        description: getMeta("description") || getMeta("og:description") || getMeta("twitter:description"),
                        keywords: getMeta("keywords"),
                        og_title: getMeta("og:title"),
                        og_image: getMeta("og:image"),
                        twitter_card: getMeta("twitter:card"),
                        canonical: document.querySelector("link[rel='canonical']") ? document.querySelector("link[rel='canonical']").getAttribute("href") : ""
                    };

                    // Link Harvest
                    const baseDomain = window.location.hostname;
                    document.querySelectorAll("a[href]").forEach(a => {
                        const href = a.getAttribute("href").trim();
                        if (href.startsWith("mailto:")) {
                            data.links.email.push(href);
                        } else if (href.startsWith("tel:")) {
                            data.links.tel.push(href);
                        } else if (href.startsWith("http") || href.startsWith("//")) {
                            try {
                                const urlObj = new URL(href, window.location.href);
                                if (urlObj.hostname === baseDomain) {
                                    data.links.internal.push(urlObj.href);
                                } else {
                                    data.links.external.push(urlObj.href);
                                }
                            } catch(e) {
                                data.links.external.push(href);
                            }
                        } else {
                            try {
                                const urlObj = new URL(href, window.location.href);
                                data.links.internal.push(urlObj.href);
                            } catch(e) {
                                data.links.internal.push(href);
                            }
                        }
                    });

                    return data;
                })();
                """
                
                extracted_dom = await page.evaluate(eval_js)
                js_charts = extracted_dom.get("js_charts", [])
                canvas_charts = extracted_dom.get("canvas_charts", [])
                svg_charts = extracted_dom.get("svg_charts", [])
                embedded_docs = extracted_dom.get("embedded_docs", [])
                metadata = extracted_dom.get("metadata", {})
                links = extracted_dom.get("links", {})
                
                await browser.close()
        except Exception as playwright_err:
            logger.warning(f"[ENTERPRISE SCRAPER] Playwright scrape failed: {playwright_err}. Attempting requests fallback...")
            try:
                fallback_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9"
                }
                res = requests.get(url, headers=fallback_headers, timeout=20)
                html_content = res.text
                soup = BeautifulSoup(html_content, "html.parser")
                title = soup.title.string.strip() if soup.title else "Scraped Document"
                
                # Extract basic tags from metadata
                def get_meta_tag(name):
                    el = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
                    return el.get("content", "") if el else ""
                
                metadata = {
                    "title": title,
                    "description": get_meta_tag("description") or get_meta_tag("og:description"),
                    "keywords": get_meta_tag("keywords"),
                    "og_title": get_meta_tag("og:title"),
                    "og_image": get_meta_tag("og:image"),
                    "twitter_card": get_meta_tag("twitter:card"),
                    "canonical": soup.find("link", rel="canonical").get("href", "") if soup.find("link", rel="canonical") else ""
                }
                
                # Extract links from page
                base_domain = urlparse(url).netloc
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if href.startswith("mailto:"):
                        links["email"].append(href)
                    elif href.startswith("tel:"):
                        links["tel"].append(href)
                    elif href.startswith("http") or href.startswith("//"):
                        try:
                            url_obj = urlparse(urljoin(url, href))
                            if url_obj.netloc == base_domain:
                                links["internal"].append(urljoin(url, href))
                            else:
                                links["external"].append(urljoin(url, href))
                        except Exception:
                            links["external"].append(href)
                    else:
                        links["internal"].append(urljoin(url, href))
                
                # Deduplicate links
                links["internal"] = list(set(links["internal"]))
                links["external"] = list(set(links["external"]))
                links["email"] = list(set(links["email"]))
                links["tel"] = list(set(links["tel"]))
                
            except Exception as requests_err:
                logger.error(f"[ENTERPRISE SCRAPER] Requests fallback failed: {requests_err}")
                html_content = "<html><head><title>Page Unavailable</title></head><body>Content could not be retrieved.</body></html>"
                soup = BeautifulSoup(html_content, "html.parser")
                title = "Page Unavailable"
                metadata = {
                    "title": title,
                    "description": "Page content could not be retrieved.",
                    "keywords": "",
                    "og_title": "",
                    "og_image": "",
                    "twitter_card": "",
                    "canonical": ""
                }
            
        # HTML Tables Structured Extraction
        tables_data = []
        for idx, table in enumerate(soup.find_all("table")):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cells:
                    rows.append(cells)
            
            table_struct = {"index": idx, "headers": headers, "rows": rows}
            tables_data.append(table_struct)
            
            table_filename = f"{output_dirs['tables']}/{slug}_table_{idx}.json"
            with open(table_filename, "w", encoding="utf-8") as f:
                json.dump(table_struct, f, indent=4, ensure_ascii=False)
            logger.info(f"[ENTERPRISE SCRAPER] Extracted HTML Table {idx} to {table_filename}")

        # Images Extraction & OCR (with Tesseract)
        image_metadata = []
        for idx, img_tag in enumerate(soup.find_all("img")):
            img_src = img_tag.get("src", "")
            if not img_src:
                continue
            img_url = urljoin(url, img_src)
            alt_text = img_tag.get("alt", "")
            
            try:
                img_res = requests.get(img_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if img_res.status_code == 200:
                    img_ext = os.path.splitext(urlparse(img_url).path)[1] or ".png"
                    if img_ext.lower() not in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
                        img_ext = ".png"
                    
                    img_filename = f"{slug}_img_{idx}{img_ext}"
                    img_filepath = os.path.join(output_dirs["images"], img_filename)
                    
                    with open(img_filepath, "wb") as f:
                        f.write(img_res.content)
                    
                    ocr_text = ""
                    try:
                        from PIL import Image
                        import pytesseract
                        tesseract_default_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                        if os.path.exists(tesseract_default_path):
                            pytesseract.pytesseract.tesseract_cmd = tesseract_default_path
                        pil_img = Image.open(img_filepath)
                        ocr_text = pytesseract.image_to_string(pil_img).strip()
                    except Exception as ocr_err:
                        logger.warning(f"OCR failed for {img_filepath}: {ocr_err}")
                    
                    image_metadata.append({
                        "image_url": img_url,
                        "alt_text": alt_text,
                        "page_url": url,
                        "filename": img_filename,
                        "ocr_text": ocr_text
                    })
                    logger.info(f"[ENTERPRISE SCRAPER] Downloaded image {idx} & extracted OCR text length: {len(ocr_text)}")
            except Exception as img_err:
                logger.warning(f"Failed to download image {img_url}: {img_err}")
                
        # PDF Detection, Download & Text Extraction (PyMuPDF)
        pdf_metadata = []
        for idx, link_tag in enumerate(soup.find_all("a", href=True)):
            link_href = link_tag["href"]
            if link_href.lower().endswith(".pdf"):
                pdf_url = urljoin(url, link_href)
                
                try:
                    pdf_res = requests.get(pdf_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                    if pdf_res.status_code == 200:
                        pdf_filename = f"{slug}_pdf_{idx}.pdf"
                        pdf_filepath = os.path.join(output_dirs["pdfs"], pdf_filename)
                        
                        with open(pdf_filepath, "wb") as f:
                            f.write(pdf_res.content)
                        
                        pdf_text = ""
                        try:
                            import fitz
                            pdf_doc = fitz.open(pdf_filepath)
                            for page_num in range(len(pdf_doc)):
                                pdf_text += pdf_doc[page_num].get_text()
                        except Exception as pdf_err:
                            logger.warning(f"PyMuPDF failed to extract text from {pdf_filepath}: {pdf_err}")
                        
                        pdf_text_filepath = os.path.join(output_dirs["pdfs"], f"{slug}_pdf_{idx}.txt")
                        with open(pdf_text_filepath, "w", encoding="utf-8") as f:
                            f.write(pdf_text)
                        
                        pdf_metadata.append({
                            "pdf_url": pdf_url,
                            "filename": pdf_filename,
                            "page_url": url,
                            "extracted_text_file": f"{slug}_pdf_{idx}.txt",
                            "text_length": len(pdf_text)
                        })
                        logger.info(f"[ENTERPRISE SCRAPER] Downloaded PDF {idx} & extracted {len(pdf_text)} characters")
                except Exception as pdf_dl_err:
                    logger.warning(f"Failed to download PDF {pdf_url}: {pdf_dl_err}")

        # Save Charts & SVG data
        charts_package = {
            "page_url": url,
            "js_charts": js_charts,
            "canvas_charts": canvas_charts,
            "svg_charts": svg_charts
        }
        charts_filename = f"{output_dirs['charts']}/{slug}_charts.json"
        with open(charts_filename, "w", encoding="utf-8") as f:
            json.dump(charts_package, f, indent=4, ensure_ascii=False)

        # Save Captured Network/API Logs
        network_filename = f"{output_dirs['network']}/{slug}_network.json"
        with open(network_filename, "w", encoding="utf-8") as f:
            json.dump(network_logs, f, indent=4, ensure_ascii=False)

        # Save Page Metadata & Links & OCR text
        metadata_package = {
            "page_url": url,
            "title": title,
            "metadata_tags": metadata,
            "extracted_links": links,
            "embedded_documents": embedded_docs,
            "images": image_metadata,
            "pdfs": pdf_metadata
        }
        metadata_filename = f"{output_dirs['metadata']}/{slug}_metadata.json"
        with open(metadata_filename, "w", encoding="utf-8") as f:
            json.dump(metadata_package, f, indent=4, ensure_ascii=False)

        # Retrieve Crawl4AI markdown representation
        markdown_text = ""
        try:
            async with AsyncWebCrawler(verbose=True) as crawler:
                c4ai_res = await crawler.arun(
                    url=url,
                    cache_mode=CacheMode.BYPASS,
                    bypass_robots=True
                )
                if c4ai_res.success:
                    markdown_text = c4ai_res.markdown
                else:
                    logger.warning(f"Crawl4AI markdown extraction failed: {c4ai_res.error_message}")
        except Exception as e:
            logger.warning(f"Crawl4AI markdown runtime error: {e}")
            
        if not markdown_text:
            try:
                import html2text
                converter = html2text.HTML2Text()
                converter.ignore_links = False
                markdown_text = converter.handle(html_content)
            except Exception:
                markdown_text = soup.get_text()

        # Save cleaned page text markdown
        # Convert extracted structured tables to markdown and append to markdown_text
        if tables_data:
            table_md_blocks = []
            for t_struct in tables_data:
                headers = t_struct.get("headers", [])
                rows = t_struct.get("rows", [])
                if not headers and not rows:
                    continue
                # Pad/build headers if they are empty
                if not headers and rows:
                    headers = [f"Col {col_idx+1}" for col_idx in range(len(rows[0]))]
                
                md_rows = []
                md_rows.append("| " + " | ".join(headers) + " |")
                md_rows.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for row in rows:
                    padded_row = list(row) + [""] * (len(headers) - len(row))
                    md_rows.append("| " + " | ".join(str(cell) for cell in padded_row[:len(headers)]) + " |")
                
                table_md_blocks.append("\n".join(md_rows))
            
            if table_md_blocks:
                markdown_text += "\n\n### Extracted Data Tables\n\n" + "\n\n".join(table_md_blocks)

        page_filename = f"{output_dirs['pages']}/{slug}.txt"
        with open(page_filename, "w", encoding="utf-8") as f:
            f.write(markdown_text)
        logger.info(f"[ENTERPRISE SCRAPER] Saved page markdown text to {page_filename}")

        return {
            "title": title,
            "markdown": markdown_text,
            "url": url
        }

    @staticmethod
    async def run_multi_enterprise_scrape_async(base_url: str, max_subpages: int = 5) -> list:
        """
        Gathers internal sublinks, then executes concurrent enterprise scrapes.
        """
        custom_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        
        logger.info(f"[MULTI-SCRAPER] Harvesting links from base index page: {base_url}")
        target_urls = [base_url]
        
        try:
            async with AsyncWebCrawler(verbose=True) as crawler:
                index_res = await crawler.arun(
                    url=base_url,
                    cache_mode=CacheMode.BYPASS,
                    bypass_robots=True,
                    extra_headers=custom_headers
                )
                if index_res.success:
                    soup = BeautifulSoup(index_res.html, "html.parser")
                    base_domain = urlparse(base_url).netloc
                    
                    links_to_crawl = []
                    for anchor in soup.find_all("a", href=True):
                        href = anchor["href"]
                        full_url = urljoin(base_url, href)
                        
                        if urlparse(full_url).netloc == base_domain and full_url != base_url:
                            if full_url not in links_to_crawl:
                                links_to_crawl.append(full_url)
                    
                    target_urls.extend(links_to_crawl[:max_subpages])
        except Exception as e:
            logger.error(f"[MULTI-SCRAPER] Harvesting failed: {e}. Defaulting to base URL only.")
            
        logger.info(f"[MULTI-SCRAPER] Crawling {len(target_urls)} pages concurrently...")
        
        tasks = [WebScraper.run_enterprise_scrape_async(url) for url in target_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        scraped_pages = []
        for url, res in zip(target_urls, results):
            if isinstance(res, Exception):
                logger.error(f"[MULTI-SCRAPER ERROR] Failed to crawl: {url}. Error: {res}")
            else:
                scraped_pages.append(res)
                
        return scraped_pages

    @staticmethod
    def run_crawler_sync(url: str) -> dict:
        """
        Spawns a private event loop to crawl a single URL.
        """
        loop = asyncio.new_event_loop()
        try:
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            return loop.run_until_complete(WebScraper.run_enterprise_scrape_async(url))
        finally:
            loop.close()

    @staticmethod
    def run_multi_crawler_sync(base_url: str, max_subpages: int = 5) -> list:
        """
        Gathers and crawls sublinks concurrently.
        """
        loop = asyncio.new_event_loop()
        try:
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            return loop.run_until_complete(WebScraper.run_multi_enterprise_scrape_async(base_url, max_subpages))
        finally:
            loop.close()

    @staticmethod
    def save_scraped_data_to_json(article_data: dict, file_path: str = "data/raw_crawled_urls.json"):
        """
        Saves crawled article dictionary into a local JSON list cache.
        """
        articles = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    articles = json.load(f)
            except Exception:
                articles = []
                
        articles.append(article_data)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=4, ensure_ascii=False)
        logger.info(f"[DISK CACHE] Saved raw scraped article to: {file_path}")

    @staticmethod
    def load_latest_scraped_article(file_path: str = "data/raw_crawled_urls.json") -> dict:
        """
        Loads the latest crawled article from the local JSON list cache.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Staging file {file_path} not found.")
        with open(file_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        if not articles:
            raise ValueError(f"No records found in {file_path}")
        return articles[-1]
