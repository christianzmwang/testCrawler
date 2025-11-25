import requests
import socket
import ssl
import re
import time
from urllib.parse import urlparse
from datetime import datetime
import warnings

# Suppress SSL warnings
warnings.filterwarnings("ignore")

class DomainAnalyzer:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        # Regex patterns
        self.patterns = {
            'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            'phone': r'(\+\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}',
            
            # CMS
            'cms_wordpress': [r'wp-content', r'wp-includes', r'wordpress'],
            'cms_drupal': [r'Drupal', r'sites/default/files'],
            'cms_joomla': [r'Joomla', r'option=com_'],
            'cms_typo3': [r'TYPO3'],
            'cms_shopify': [r'myshopify\.com', r'cdn\.shopify\.com'],
            'cms_wix': [r'wix\.com', r'wix-dns'],
            'cms_squarespace': [r'squarespace\.com', r'static1\.squarespace'],
            'cms_webflow': [r'webflow\.com', r'w-mod-'],
            'cms_ghost': [r'ghost\.org', r'ghost-sdk'],
            'cms_duda': [r'duda\.co', r'duda-static'],
            'cms_craft': [r'Craft CMS'],
            
            # Ecommerce
            'ecom_woocommerce': [r'woocommerce'],
            'ecom_magento': [r'magento', r'mage/'],
            
            # Payments
            'pay_stripe': [r'stripe\.com', r'__stripe'],
            'pay_paypal': [r'paypal\.com', r'paypal_objects'],
            'pay_klarna': [r'klarna\.com', r'klarna-checkout'],
            
            # Analytics
            'analytics_ga4': [r'G-[A-Z0-9]{10}'],
            'analytics_gtm': [r'googletagmanager\.com', r'GTM-'],
            'analytics_ua': [r'UA-\d+-\d+'],
            'analytics_fb_pixel': [r'connect\.facebook\.net', r'fbq\('],
            'analytics_linkedin': [r'linkedin\.com/insight', r'snap\.licdn\.com'],
            'analytics_hotjar': [r'hotjar\.com', r'hjid'],
            'analytics_hubspot': [r'hs-scripts\.com', r'hubspot\.com'],
            
            # JS Frameworks
            'js_react': [r'react', r'react-dom', r'data-reactroot'],
            'js_vue': [r'vue\.js', r'data-v-', r'__vue__'],
            'js_angular': [r'angular', r'ng-version', r'ng-app'],
            'js_nextjs': [r'/_next/', r'__NEXT_DATA__'],
            'js_nuxt': [r'/_nuxt/', r'__NUXT__'],
            'js_svelte': [r'svelte-'],
            
            # Risk Keywords
            'risk_placeholder_kw': [r'lorem ipsum', r'coming soon', r'under construction'],
            'risk_parked_kw': [r'domain parked', r'for sale', r'buy this domain'],
            'risk_suspended_kw': [r'account suspended', r'cgi-sys/suspendedpage'],
        }

    def analyze(self, url):
        result = {
            'domain': url,
            'timestamp': datetime.now().isoformat(),
            'errors': ''
        }
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            
            # 1. DNS & IP
            try:
                result['ip'] = socket.gethostbyname(domain)
            except:
                result['ip'] = ''
                result['errors'] += 'DNS_FAIL;'

            # 2. TLS/SSL
            try:
                context = ssl.create_default_context()
                with socket.create_connection((domain, 443), timeout=5) as sock:
                    with context.wrap_socket(sock, server_hostname=domain) as ssock:
                        cert = ssock.getpeercert()
                        
                        not_before = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y %Z')
                        not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                        
                        result['tls_valid'] = True
                        result['tls_not_before'] = not_before.strftime('%Y-%m-%d')
                        result['tls_not_after'] = not_after.strftime('%Y-%m-%d')
                        result['tls_days_to_expiry'] = (not_after - datetime.now()).days
                        
                        # Issuer
                        issuer = dict(x[0] for x in cert['issuer'])
                        result['tls_issuer'] = issuer.get('organizationName', issuer.get('commonName', 'Unknown'))
            except Exception as e:
                result['tls_valid'] = False
                result['tls_not_before'] = ''
                result['tls_not_after'] = ''
                result['tls_days_to_expiry'] = ''
                result['tls_issuer'] = ''
                if 'SSL' in str(e) or 'Certificate' in str(e):
                    result['errors'] += f'SSL_FAIL({str(e)});'

            # 3. HTTP Request
            start_time = time.time()
            try:
                response = requests.get(url, headers=self.headers, timeout=10, verify=False)
                result['elapsed_ms'] = int((time.time() - start_time) * 1000)
                
                # Headers
                result['header_server'] = response.headers.get('Server', '')
                result['header_x_powered_by'] = response.headers.get('X-Powered-By', '')
                result['security_hsts'] = 'Strict-Transport-Security' in response.headers
                result['security_csp'] = 'Content-Security-Policy' in response.headers
                result['cookies_present'] = len(response.cookies) > 0
                
                # Hints
                result['server_hint'] = result['header_server']
                result['cdn_hint'] = self._detect_cdn(response.headers)
                
                # Content Analysis
                html = response.text
                html_lower = html.lower()
                
                result['html_kb'] = round(len(html) / 1024, 2)
                result['html_kb_over_500'] = result['html_kb'] > 500
                
                # Regex Checks
                self._run_regex_checks(html, html_lower, result)
                
                # Specific Logic
                result['has_email_text'] = bool(re.search(self.patterns['email'], html))
                result['has_phone_text'] = bool(re.search(self.patterns['phone'], html))
                
                # CMS Logic
                result['primary_cms'] = self._determine_primary_cms(result)
                
                # Risk Flags
                risk_flags = []
                if result['risk_placeholder_kw']: risk_flags.append('placeholder')
                if result['risk_parked_kw']: risk_flags.append('parked')
                if result['risk_suspended_kw']: risk_flags.append('suspended')
                if not result['tls_valid']: risk_flags.append('no_tls')
                result['risk_flags'] = ','.join(risk_flags)
                
            except Exception as e:
                result['elapsed_ms'] = 0
                result['errors'] += f'HTTP_FAIL({str(e)});'
                # Fill defaults for missing fields
                self._fill_defaults(result)

        except Exception as e:
            result['errors'] += f'CRITICAL({str(e)});'
            
        return result

    def _detect_cdn(self, headers):
        cdn_headers = ['cf-ray', 'x-amz-cf-id', 'x-azure-ref', 'x-goog-generation', 'server']
        for h in cdn_headers:
            val = headers.get(h, '').lower()
            if 'cloudflare' in val: return 'Cloudflare'
            if 'cloudfront' in val: return 'CloudFront'
            if 'azure' in val: return 'Azure'
            if 'google' in val: return 'Google'
            if 'akamai' in val: return 'Akamai'
            if 'fastly' in val: return 'Fastly'
        return ''

    def _run_regex_checks(self, html, html_lower, result):
        # Check all boolean flags based on patterns
        for key, patterns in self.patterns.items():
            if key.startswith('risk_') or key in ['email', 'phone']: continue
            
            found = False
            for p in patterns:
                if re.search(p, html, re.IGNORECASE):
                    found = True
                    break
            result[key] = found
            
        # Risk keywords (count matches or just bool)
        for key in ['risk_placeholder_kw', 'risk_parked_kw', 'risk_suspended_kw']:
            found = False
            for p in self.patterns[key]:
                if re.search(p, html_lower):
                    found = True
                    break
            result[key] = found
            
        # Special WP check
        result['cms_wordpress_html'] = 'wp-content' in html_lower

    def _determine_primary_cms(self, result):
        cms_list = [k for k in result.keys() if k.startswith('cms_') and result[k] and k != 'cms_wordpress_html']
        if not cms_list: return ''
        # Simple priority or first found
        return cms_list[0].replace('cms_', '').capitalize()

    def _fill_defaults(self, result):
        # Ensure all keys exist with default False/Empty
        keys = [
            'header_server', 'header_x_powered_by', 'security_hsts', 'security_csp',
            'cookies_present', 'cdn_hint', 'server_hint', 'html_kb', 'html_kb_over_500',
            'has_email_text', 'has_phone_text', 'primary_cms', 'risk_flags',
            'cms_wordpress_html'
        ]
        for k in keys:
            if k not in result: result[k] = '' if 'hint' in k or 'server' in k or 'cms' in k or 'flags' in k else False
            
        for key in self.patterns.keys():
            if key not in ['email', 'phone'] and key not in result:
                result[key] = False

