"""
Tema Dark Customizado para YouTube Transcriber
Inspirado em VS Code Dark+
"""

from gui.widgets.treeview_style import apply_treeview_row_style

def apply_dark_theme(root, style):
    """
    Aplica tema escuro personalizado ao app
    
    Args:
        root: tk.Tk - janela principal
        style: ttk.Style - objeto de estilo
    
    Returns:
        dict: Configurações para widgets Text (não-ttk)
    """
    
    # === PALETA DE CORES ===
    colors = {
        # Backgrounds
        'bg_darkest': '#1e1e1e',      # Fundo mais escuro
        'bg_dark': '#252526',          # Fundo escuro
        'bg_medium': '#2d2d30',        # Fundo médio (hover)
        'bg_light': '#3e3e42',         # Fundo claro (seleção)
        
        # Foregrounds
        'fg_normal': '#cccccc',        # Texto normal
        'fg_bright': '#ffffff',        # Texto destacado
        'fg_dim': '#969696',           # Texto secundário
        
        # Accents
        'accent': '#0e639c',           # Azul (botões)
        'accent_hover': '#1177bb',     # Azul hover
        'accent_pressed': '#0d5a8f',   # Azul pressionado
        
        # Status colors
        'success': '#4ec9b0',          # Verde (sucesso)
        'error': '#f48771',            # Vermelho (erro)
        'warning': '#dcdcaa',          # Amarelo (aviso)
        'info': '#4fc1ff',             # Azul claro (info)
        
        # Borders
        'border': '#3e3e42',
        'border_focus': '#0e639c',
    }
    
    # === CONFIGURAR ROOT ===
    root.configure(bg=colors['bg_darkest'])
    
    # === USAR CLAM COMO BASE ===
    style.theme_use('clam')
    
    # === FRAMES ===
    style.configure("TFrame",
        background=colors['bg_darkest'],
        borderwidth=0
    )
    
    style.configure("TLabelframe",
        background=colors['bg_darkest'],
        foreground=colors['fg_bright'],
        bordercolor=colors['border'],
        borderwidth=1,
        relief='solid'
    )
    
    style.configure("TLabelframe.Label",
        background=colors['bg_darkest'],
        foreground=colors['fg_bright'],
        font=('Segoe UI', 9, 'bold')
    )
    
    # === LABELS ===
    style.configure("TLabel",
        background=colors['bg_darkest'],
        foreground=colors['fg_normal'],
        font=('Segoe UI', 9)
    )
    
    # === BUTTONS ===
    style.configure("TButton",
        background=colors['accent'],
        foreground='#ffffff',
        borderwidth=0,
        focuscolor='none',
        padding=(10, 6),
        font=('Segoe UI', 9)
    )
    
    style.map("TButton",
        background=[
            ('active', colors['accent_hover']),
            ('pressed', colors['accent_pressed']),
            ('disabled', colors['bg_medium'])
        ],
        foreground=[
            ('disabled', colors['fg_dim'])
        ]
    )
    
    # === ENTRY ===
    style.configure("TEntry",
        fieldbackground=colors['bg_dark'],
        foreground=colors['fg_normal'],
        insertcolor=colors['fg_bright'],
        bordercolor=colors['border'],
        lightcolor=colors['border'],
        darkcolor=colors['border'],
        borderwidth=1,
        padding=5
    )
    
    style.map("TEntry",
        bordercolor=[('focus', colors['border_focus'])],
        lightcolor=[('focus', colors['border_focus'])],
        darkcolor=[('focus', colors['border_focus'])]
    )
    
    # === COMBOBOX ===
    style.configure("TCombobox",
        fieldbackground=colors['bg_dark'],
        foreground=colors['fg_normal'],
        background=colors['bg_dark'],
        arrowcolor=colors['fg_normal'],
        bordercolor=colors['border'],
        lightcolor=colors['border'],
        darkcolor=colors['border'],
        borderwidth=1,
        padding=5
    )
    
    style.map("TCombobox",
        fieldbackground=[('readonly', colors['bg_dark'])],
        foreground=[('readonly', colors['fg_normal'])],
        bordercolor=[('focus', colors['border_focus'])],
        lightcolor=[('focus', colors['border_focus'])],
        darkcolor=[('focus', colors['border_focus'])]
    )
    
    # === CHECKBUTTON ===
    style.configure("TCheckbutton",
        background=colors['bg_darkest'],
        foreground=colors['fg_normal'],
        font=('Segoe UI', 9)
    )
    
    style.map("TCheckbutton",
        background=[('active', colors['bg_darkest'])],
        foreground=[('active', colors['fg_bright'])]
    )
    
    # === RADIOBUTTON ===
    style.configure("TRadiobutton",
        background=colors['bg_darkest'],
        foreground=colors['fg_normal'],
        font=('Segoe UI', 9)
    )
    
    style.map("TRadiobutton",
        background=[('active', colors['bg_darkest'])],
        foreground=[('active', colors['fg_bright'])]
    )
    
    # === NOTEBOOK (TABS) ===
    style.configure("TNotebook",
        background=colors['bg_darkest'],
        borderwidth=0,
        tabmargins=[0, 0, 0, 0]
    )
    
    style.configure("TNotebook.Tab",
        background=colors['bg_medium'],
        foreground=colors['fg_dim'],
        padding=[15, 8],
        borderwidth=0,
        font=('Segoe UI', 9)
    )
    
    style.map("TNotebook.Tab",
        background=[
            ('selected', colors['bg_darkest']),
            ('active', colors['bg_light'])
        ],
        foreground=[
            ('selected', colors['fg_bright']),
            ('active', colors['fg_normal'])
        ]
    )
    
    # === TREEVIEW ===
    apply_treeview_row_style(style)

    # === SCROLLBAR ===
    style.configure("Vertical.TScrollbar",
        background=colors['bg_medium'],
        bordercolor=colors['bg_darkest'],
        arrowcolor=colors['fg_normal'],
        troughcolor=colors['bg_darkest'],
        borderwidth=0
    )
    
    style.map("Vertical.TScrollbar",
        background=[('active', colors['bg_light'])]
    )
    
    style.configure("Horizontal.TScrollbar",
        background=colors['bg_medium'],
        bordercolor=colors['bg_darkest'],
        arrowcolor=colors['fg_normal'],
        troughcolor=colors['bg_darkest'],
        borderwidth=0
    )
    
    style.map("Horizontal.TScrollbar",
        background=[('active', colors['bg_light'])]
    )
    
    # === PROGRESSBAR ===
    style.configure("TProgressbar",
        background=colors['success'],
        troughcolor=colors['bg_dark'],
        bordercolor=colors['border'],
        lightcolor=colors['success'],
        darkcolor=colors['success'],
        borderwidth=0,
        thickness=6
    )
    
    # === SEPARATOR ===
    style.configure("TSeparator",
        background=colors['border']
    )
    
    # === RETORNAR CORES PARA WIDGETS TEXT (NÃO-TTK) ===
    return {
        'bg': colors['bg_dark'],
        'fg': colors['fg_normal'],
        'insertbackground': colors['fg_bright'],
        'selectbackground': colors['accent'],
        'selectforeground': '#ffffff',
        'highlightbackground': colors['border'],
        'highlightcolor': colors['border_focus'],
        'highlightthickness': 1,
        'font': ('Consolas', 9)
    }
