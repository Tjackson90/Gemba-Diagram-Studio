"""Diagram art direction, captured per document rather than mutable global colors."""
from contextvars import ContextVar
from contextlib import contextmanager

THEMES = {
    'Volt': dict(bg='#12161c',panel='#1d242d',ink='#f1f5f8',muted='#99a8b7',grid='#445260',root='#cefb70',note='#a7d9f8',active='#ff997c',on_root='#16200c',on_note='#132533'),
    'Paper': dict(bg='#faf9f5',panel='#eeede6',ink='#202735',muted='#637082',grid='#bcc5cb',root='#365cf5',note='#d5e0ed',active='#ed6849',on_root='#ffffff',on_note='#24344a'),
    'Prism': dict(bg='#171327',panel='#25203b',ink='#f8f3ff',muted='#afa5ca',grid='#524969',root='#b9a0ff',note='#80e1d6',active='#ffb18d',on_root='#21123e',on_note='#102f30'),
}
_theme=ContextVar('diagram_theme',default='Volt')

def name(): return _theme.get()

def palette(theme=None): return THEMES[theme or name()]

@contextmanager
def theme(value):
    if value not in THEMES: raise ValueError('Unknown diagram theme')
    token=_theme.set(value)
    try: yield
    finally: _theme.reset(token)
