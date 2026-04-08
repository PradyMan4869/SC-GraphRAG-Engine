"""
Professional CSS for Supreme Court GraphRAG UI.
Includes Gold/Dark and Blue/Light themes with glassmorphism chat bubbles.
"""

def get_custom_css(dark_mode: bool = True) -> str:
    if dark_mode:
        # Gold/Dark Theme
        bg_color = "#0e1117"
        text_color = "#fafafa"
        bubble_user = "rgba(78, 141, 245, 0.15)"  # Soft Blue
        bubble_bot = "rgba(245, 158, 11, 0.1)"   # Soft Gold
        border_color = "rgba(255, 255, 255, 0.1)"
    else:
        # Paper/Light Theme
        bg_color = "#ffffff"
        text_color = "#1e293b"
        bubble_user = "#f1f5f9"
        bubble_bot = "#fffbeb"
        border_color = "#e2e8f0"

    return f"""
    <style>
        /* Global Styles */
        .stApp {{
            background-color: {bg_color};
            color: {text_color};
        }}

        /* Chat Bubbles */
        [data-testid="stChatMessage"] {{
            border-radius: 15px;
            padding: 1rem;
            margin-bottom: 1rem;
            border: 1px solid {border_color};
            background-color: transparent !important;
        }}

        [data-testid="stChatMessage"]:nth-child(even) {{
            background-color: {bubble_bot} !important;
        }}

        [data-testid="stChatMessage"]:nth-child(odd) {{
            background-color: {bubble_user} !important;
        }}

        /* Better Typography */
        h1, h2, h3 {{
            font-weight: 700 !important;
            letter-spacing: -0.02em !important;
        }}

        /* Graph Explorer Container */
        iframe {{
            border-radius: 12px;
            border: 1px solid {border_color} !important;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        }}

        /* Metric Cards */
        [data-testid="stMetricValue"] {{
            font-size: 1.8rem !important;
            color: #4e8df5 !important;
        }}
    </style>
    """
