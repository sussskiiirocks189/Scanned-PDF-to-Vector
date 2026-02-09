import json
import os
import html
import re

# script by Ge123

# ===========================================================================
# 🛠️ Global Layout Configuration
# ===========================================================================
# These parameters determine the generated HTML style and paper specifications for printing.
# It is recommended to keep PAGE_WIDTH as a fixed pixel value to ensure consistency across different devices.

FONT_FAMILY = '"Times New Roman", "SimSun", serif'  # Body font: Serif preferred
FONT_SIZE_BODY = "18px"         # Body font size
FONT_SIZE_TITLE = "22px"        # Title font size
FONT_SIZE_CAPTION = "17px"      # Image/Caption font size
LINE_HEIGHT_BODY = "1.5"        # Line height
EQ_MARGIN_Y = "0px"             # Equation top/bottom margin
PARA_MARGIN_BOTTOM = "5px"      # Margin after paragraph
TITLE_MARGIN_TOP = "28px"       # Title top margin
TITLE_MARGIN_BOTTOM = "12px"    # Title bottom margin
IMG_MARGIN_Y = "16px"           # Image top/bottom margin

# Core page size configuration
PAGE_WIDTH = "580px"            # Page content width (approx. A4 width minus margins)
IMG_MAX_WIDTH = "85%"           # Max image width limit
IMG_MAX_HEIGHT = "auto"         # Image height auto-adaptive
PAGE_PADDING = "35px 42px 55px 42px" # Page padding (Top Right Bottom Left)

# Input/Output file paths
INPUT_FILE = "model.json"       # Input MinerU parse result
OUTPUT_FILE = "book_output.html" # Output HTML filename
# ===========================================================================


def extract_text_nested(block):
    """
    Helper function to recursively extract text content.
    
    Logic explanation:
    1. MinerU data structure is often nested (blocks within blocks), requiring recursion.
    2. Special handling for 'inline_equation' type:
       - Original content usually doesn't have $ symbols.
       - We need to manually add $ wrapper for MathJax recognition.
    """
    text_content = ""
    
    # Case 1: If current block contains sub-blocks, extract recursively
    if 'blocks' in block:
        for sub_block in block['blocks']:
            sub_text = extract_text_nested(sub_block)
            if sub_text:
                text_content += sub_text + "\n"
                
    # Case 2: Process lines and spans - the lowest text units
    elif 'lines' in block:
        for line in block['lines']:
            for span in line.get('spans', []):
                content = span.get('content', '')
                span_type = span.get('type', 'text')
                
                # [Core Logic] Identify and mark inline equations
                if span_type == 'inline_equation':
                    # Remove existing $ in original content to avoid duplication
                    clean_tex = content.replace('$', '').strip()
                    # Force wrap with single dollar sign, preserving original spacing
                    text_content += f"${clean_tex}$"
                else:
                    # Concatenate normal text directly
                    text_content += content
            
            # Add a space after each line to prevent word concatenation
            text_content += " "
        
        # Remove trailing whitespace
        text_content = text_content.strip() + " "
        
    # Case 3: Fallback for plain text
    elif 'text' in block:
        text_content = block['text']
        
    return text_content.strip()


def extract_image_deep(block):
    """
    Deep search for image paths.
    
    Logic explanation:
    Sometimes image_path is hidden deep in nested structures or JSON structure is inconsistent.
    This function tries direct access, then recursive search, and finally a regex fallback.
    """
    if 'image_path' in block: return block['image_path']
    if 'blocks' in block:
        for sub in block['blocks']:
            res = extract_image_deep(sub)
            if res: return res
    if 'lines' in block:
        for line in block['lines']:
            for span in line.get('spans', []):
                if 'image_path' in span: return span['image_path']
    
    # Regex fallback: Convert block to string and brute-force search
    block_str = json.dumps(block)
    match = re.search(r'"image_path":\s*"(.*?)"', block_str)
    if match: return match.group(1)
    return ""


def smart_latex_fix(text):
    """
    [Core Algorithm] Intelligent LaTeX equation completion and repair
    
    Background:
    PDF parsing often loses $ symbols or breaks equations into multiple tokens.
    This function heuristically rules to wrap potential equation text with $.
    
    Flow:
    1. Protect: First protect valid $$...$$ or $...$ to prevent double processing.
    2. Clean: Identify long text misclassifications (e.g., long English sentences mistaken as equations) and restore them.
    3. Scan: Split by spaces and check for math characteristic characters (like \ _ ^ { =).
    4. Stitch (Critical): If standalone operators (like = < >) are found, try merging surrounding tokens into one equation.
    """
    if not text: return text

    # --- Internal Function: False Positive Cleanup ---
    def clean_false_positive(match):
        full_str = match.group(0)
        inner_str = match.group(1)
        # Rule: If content is long (>7 chars) and has no math symbols, treat as text misclassification
        if len(inner_str) > 7:
            math_triggers = {'\\', '_', '^', '=', '{', '}', '<', '>'}
            if not any(char in inner_str for char in math_triggers):
                return inner_str
        return full_str

    # Execute false positive cleanup
    text = re.sub(r'\$\$([^\$]+)\$\$', clean_false_positive, text)
    text = re.sub(r'\$([^\$]+)\$', clean_false_positive, text)

    # --- Step 0: Protection Mechanism ---
    # Replace valid LaTeX equations with placeholders to prevent damage during subsequent steps
    placeholders = []
    def save_existing(match):
        placeholders.append(match.group(0))
        return f"__SAVED_LATEX_{len(placeholders)-1}__"
    text = re.sub(r'(\$\$[\s\S]*?\$\$|\$[^\$]+\$)', save_existing, text)

    # --- Step 1: Quick Filter ---
    # If text contains no math characteristic chars, return immediately (restore placeholders)
    triggers = {'_', '\\', '{', '}', '=', '^', '>', '<'} 
    if not any(char in text for char in triggers) and "\\begin" not in text:
         text = re.sub(r'__SAVED_LATEX_(\d+)__', lambda m: placeholders[int(m.group(1))], text)
         return text
    
    # --- Step 2: Token Scanning and Preliminary Marking ---
    tokens = re.split(r'(\s+)', text)
    pass1_tokens = []
    i = 0
    n = len(tokens)
    while i < n:
        current_token = tokens[i]
        
        # Skip empty tokens and protected equations
        if not current_token.strip() or "__SAVED_LATEX_" in current_token:
            pass1_tokens.append(current_token)
            i += 1
            continue
        
        # Detect LaTeX environments (e.g., \begin{equation})
        env_match = re.search(r'\\begin\{([^}]+)\}', current_token)
        if env_match:
            env_name = env_match.group(1)
            target_end = f"\\end{{{env_name}}}"
            combined = current_token
            idx = i + 1
            # Look ahead for corresponding \end{} and merge into one block
            found = (target_end in current_token)
            while not found and idx < n:
                nxt = tokens[idx]
                combined += nxt
                if target_end in nxt: found = True
                idx += 1
            pass1_tokens.append(f"$${combined}$$") # Environments are usually block equations
            i = idx
            continue
            
        # Detect math characteristic characters
        if any(char in current_token for char in triggers):
            combined = current_token
            # Parenthesis balance check: Ensure { } and ( ) are paired
            # If unbalanced, equation might be truncated by spaces, merge tokens forward
            c_open, c_close = combined.count('{'), combined.count('}')
            p_open, p_close = combined.count('('), combined.count(')')
            idx = i + 1
            while (c_open != c_close or p_open != p_close) and idx < n:
                nxt = tokens[idx]
                combined += nxt
                c_open += nxt.count('{')
                c_close += nxt.count('}')
                p_open += nxt.count('(')
                p_close += nxt.count(')')
                idx += 1
            
            if combined.strip(): 
                pass1_tokens.append(f"${combined}$") # Mark as inline equation
            else: 
                pass1_tokens.append(combined)
            i = idx
        else: 
            pass1_tokens.append(current_token)
        i += 1

    # --- Step 3: Merging Logic ---
    # Handle broken cases like "$x$ = $y$", merge into "$x = y$"
    merged_tokens = []
    j = 0
    m = len(pass1_tokens)
    while j < m:
        curr = pass1_tokens[j]
        is_rel_block = False
        
        # Check if current token is a standalone relational operator (e.g., =, <, >)
        if curr.startswith('$') and not curr.startswith('$$'):
            content = curr.replace('$', '').strip()
            if content in ['=', '>', '<', '\\approx', '\\leq', '\\geq', '\\equiv', '\\neq']: 
                is_rel_block = True
        
        if is_rel_block:
            # Look left: Is the previous non-empty token an equation?
            left_idx = len(merged_tokens) - 1
            while left_idx >= 0 and not merged_tokens[left_idx].strip(): left_idx -= 1
            can_merge_left = False
            if left_idx >= 0:
                prev = merged_tokens[left_idx]
                if prev.startswith('$') and not prev.startswith('$$') and "__SAVED_LATEX_" not in prev: 
                    can_merge_left = True
            
            # Look right: Is the next non-empty token an equation?
            right_idx = j + 1
            while right_idx < m and not pass1_tokens[right_idx].strip(): right_idx += 1
            can_merge_right = False
            if right_idx < m:
                next_t = pass1_tokens[right_idx]
                if next_t.startswith('$') and not next_t.startswith('$$') and "__SAVED_LATEX_" not in next_t: 
                    can_merge_right = True
            
            # Execute merge
            if can_merge_left and can_merge_right:
                # Left + Mid + Right merge
                left_content = merged_tokens[left_idx][1:-1]
                right_content = pass1_tokens[right_idx][1:-1]
                gap_left = "".join(merged_tokens[left_idx+1:])
                gap_right = "".join(pass1_tokens[j+1 : right_idx])
                curr_content = curr[1:-1]
                new_block = f"${left_content}{gap_left}{curr_content}{gap_right}{right_content}$"
                del merged_tokens[left_idx:] 
                merged_tokens.append(new_block)
                j = right_idx + 1
                continue
            elif can_merge_left:
                # Left + Mid merge
                left_content = merged_tokens[left_idx][1:-1]
                curr_content = curr[1:-1]
                gap_left = "".join(merged_tokens[left_idx+1:])
                new_block = f"${left_content}{gap_left}{curr_content}$"
                del merged_tokens[left_idx:]
                merged_tokens.append(new_block)
                j += 1
                continue
            elif can_merge_right:
                # Mid + Right merge
                right_content = pass1_tokens[right_idx][1:-1]
                curr_content = curr[1:-1]
                gap_right = "".join(pass1_tokens[j+1 : right_idx])
                new_block = f"${curr_content}{gap_right}{right_content}$"
                merged_tokens.append(new_block)
                j = right_idx + 1
                continue
        
        merged_tokens.append(curr)
        j += 1
        
    final_text = "".join(merged_tokens)
    # Restore previously protected equations
    final_text = re.sub(r'__SAVED_LATEX_(\d+)__', lambda m: placeholders[int(m.group(1))], final_text)
    return final_text


def json_to_html(json_path, output_path):
    print(f"📖 Reading file: {json_path}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found {json_path}")
        return

    # =======================================================================
    # HTML Template Generation
    # Note: In f-strings, CSS braces { } need to be escaped as {{ }}
    # =======================================================================
    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Document</title>
    <style>
        /* Global box model: Ensure padding doesn't expand width */
        * {{ box-sizing: border-box; }}

        body {{
            font-family: {FONT_FAMILY};
            line-height: {LINE_HEIGHT_BODY};  
            font-size: {FONT_SIZE_BODY};      
            background-color: #525659; /* Dark background for preview */
            margin: 0; padding: 20px; color: #000;
        }}
        
        /* Page Container (.page-container)
           The physical carrier of each page, fixed dimensions.
           Parent set to position: relative to provide base for absolute positioning of page numbers.
        */
        .page-container {{
            width: {PAGE_WIDTH}; 
            height: 1050px; 
            margin: 0 auto 30px auto;
            background-color: #fff;
            padding: {PAGE_PADDING}; 
            box-shadow: 0 4px 15px rgba(0,0,0,0.3); 
            position: relative; 
            overflow: hidden; 
        }}
        
        /*
           Content Wrapper (.content-wrapper)
           Contains all body text.
           Scaling logic applies only to this element, not affecting the sibling page numbers.
           Origin set to top left to coordinate with the width compensation algorithm.
        */
        .content-wrapper {{ 
            width: 100%; 
            transform-origin: top left; 
        }}
        
        /* Print Styles (@media print) */
        @media print {{
            body {{ background-color: #fff; margin: 0; padding: 0; }}
            .page-container {{
                box-shadow: none; 
                margin: 0; 
                width: {PAGE_WIDTH}; 
                height: 1050px;
                padding: {PAGE_PADDING};
                page-break-after: always; /* Force page break */
                overflow: hidden; 
            }}
            
            /* Enforce paper size to achieve WYSIWYG */
            @page {{ 
                size: {PAGE_WIDTH} 1050px; 
                margin: 0; 
            }}
        }}

        /* Page Marker (.page-marker)
           Absolute positioning at bottom center.
           Since it's outside content-wrapper, it won't scale with text; position remains fixed.
        */
        .page-marker {{ 
            position: absolute; 
            bottom: 15px;       
            left: 50%;          
            transform: translateX(-50%); 
            font-size: 14px; 
            color: #000;        
            font-family: "Times New Roman", serif;
            z-index: 999;
        }}

        /* Other layout styles */
        .title-block {{
            font-size: {FONT_SIZE_TITLE};       
            font-weight: bold;
            margin-top: {TITLE_MARGIN_TOP};       
            margin-bottom: {TITLE_MARGIN_BOTTOM}; 
        }}
        .equation-block {{
            margin: {EQ_MARGIN_Y} 0;  
            text-align: center;
        }}
        p {{ margin-bottom: {PARA_MARGIN_BOTTOM}; text-align: justify; }}
        img {{
            max-width: {IMG_MAX_WIDTH}; max-height: {IMG_MAX_HEIGHT};
            display: block; margin: {IMG_MARGIN_Y} auto;
            /* Force browser to render image immediately (Safari Fix) */
            loading: eager;
            content-visibility: visible;
        }}
        .caption-block {{
            font-size: {FONT_SIZE_CAPTION}; color: #666; text-align: center;
            font-style: italic;
        }}
    </style>
    
    <script>
    /**
     * Auto-Zoom Logic
     * Detect if page content overflows height; if so, scale down proportionally.
     * Also compensates width to ensure it still fills the page visually.
     */
    function fitContentToPage() {{
        const CONTAINER_HEIGHT = 1050;
        const PADDING_TOP = 35;
        const PADDING_BOTTOM = 55;
        // Calculate safe content height after removing padding
        const SAFE_HEIGHT = CONTAINER_HEIGHT - PADDING_TOP - PADDING_BOTTOM; 
        
        const pages = document.querySelectorAll('.page-container');
        console.log("Executing content auto-zoom...");
        
        pages.forEach((page, index) => {{
            const wrapper = page.querySelector('.content-wrapper');
            if (!wrapper) return;
            
            const contentHeight = wrapper.offsetHeight;
            
            // If content height overflows
            if (contentHeight > SAFE_HEIGHT) {{
                const ratio = SAFE_HEIGHT / contentHeight;
                console.log(`Page ${{index+1}} overflow, scaling: ${{ratio}}`);
                
                // 1. Width compensation: Increase container width to offset visual narrowing from scale
                wrapper.style.width = `${{100 / ratio}}%`;
                // 2. Overall scaling
                wrapper.style.transform = `scale(${{ratio}})`;
            }}
        }});
    }}
    
    // MathJax Configuration
    MathJax = {{
      options: {{ 
          // Expand lazy load margin, force render equations outside viewport (Safari Fix)
          lazyMargin: "200%" 
      }},
      tex: {{ inlineMath: [['$', '$']], displayMath: [['$$', '$$']] }},
      svg: {{ fontCache: 'global' }},
      startup: {{ 
        pageReady: () => {{
           return MathJax.startup.defaultPageReady().then(() => {{
             // Only execute zoom after equations are fully rendered and height is determined
             fitContentToPage();
           }});
        }}
      }}
    }};
    </script>
    <script type="text/javascript" id="MathJax-script" async
      src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js">
    </script>
</head>
<body>
    """
    
    # Compatibility: Support list or dict input formats
    pdf_info = data.get('pdf_info', [])
    if not pdf_info:
        if isinstance(data, list): pdf_info = [{'para_blocks': data}]
        elif 'content_list' in data: pdf_info = [{'para_blocks': data['content_list']}]

    page_count = 0
    
    # ===================================================================
    # Content Generation Loop
    # ===================================================================
    for page_data in pdf_info:
        page_count += 1
        
        # 1. Create page container (Relative positioning base)
        html_content += f'<div class="page-container">'
        
        # 2. Insert page marker (Absolute positioning, independent of content scaling)
        html_content += f'<div class="page-marker">{page_count}</div>'
        
        # 3. Create content wrapper (Object involved in scaling)
        html_content += f'<div class="content-wrapper">'
        
        blocks = page_data.get('para_blocks', [])
        blocks.sort(key=lambda x: x.get('index', 0))

        for block in blocks:
            b_type = block.get('type', 'text')
            
            # Process blocks with images (may contain caption)
            if b_type == 'image' and 'blocks' in block:
                img_url = extract_image_deep(block)
                caption_text = ""
                for sub in block['blocks']:
                    if sub.get('type') == 'image_caption':
                        caption_text = extract_text_nested(sub)
                        break
                if img_url: html_content += f'<img src="{img_url}">\n'
                if caption_text:
                    fixed_cap = smart_latex_fix(caption_text)
                    safe_cap = html.escape(fixed_cap, quote=False)
                    html_content += f'<div class="caption-block">{safe_cap}</div>\n'
                continue
            
            # Process plain image blocks
            elif b_type == 'image':
                img_url = extract_image_deep(block)
                if img_url: html_content += f'<img src="{img_url}">\n'
                continue

            # Process text blocks
            text_content = extract_text_nested(block)
            if not text_content: continue

            if b_type == 'title':
                html_content += f'<div class="title-block">{html.escape(text_content)}</div>\n'
            elif b_type in ['equation', 'formula', 'interline_equation']:
                clean_tex = text_content.replace('$$', '').strip()
                html_content += f'<div class="equation-block">$$ {clean_tex} $$</div>\n'
            else:
                fixed_text = smart_latex_fix(text_content)
                safe_text = html.escape(fixed_text, quote=False)
                # Preserve newlines
                final_html = safe_text.replace('\n', '<br>')
                html_content += f'<p>{final_html}</p>\n'

        # Close wrapper and container
        html_content += '</div></div>'

    # ===================================================================
    # Auto-scroll script (Safari Compatibility)
    # Purpose: Scroll to bottom then back to top to force browser to load all lazy-loaded resources
    # ===================================================================
    html_content += """
    <script>
        window.onload = function() {
            console.log("Warming up rendering...");
            setTimeout(function() {
                window.scrollTo(0, document.body.scrollHeight);
                setTimeout(function() { window.scrollTo(0, 0); }, 200);
            }, 500);
        };
    </script>
    </body></html>
    """
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"✅ Conversion complete, generated: {OUTPUT_FILE}")

if __name__ == "__main__":
    if os.path.exists(INPUT_FILE):
        json_to_html(INPUT_FILE, OUTPUT_FILE)
    else:
        print(f"❌ Error: {INPUT_FILE} not found in current directory")