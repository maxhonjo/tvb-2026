



# sources/ module structure (naming/outputs)

sources/
├── sourcename/
│   ├── __init__.py
│   ├── sourcename.py
│   ├── src/
│   │   ├── 
│   │   ├── 

[sourcename.py]
contains the get_sourcename() function to collect data

[__init__.py]
re-exports get_sourcename() so the main application can import it directly

[src/]
everything else the source needs (platform-specific code, helpers, binaries)

**usage**
Core application imports get_sourcename():
```py
    from sources.sourcename import get_sourcename
```





# current sources

sources/
├── location/
│   ├── __init__.py
│   ├── location.py              >> get_location()
│   ├── src/
│   │   ├── mac.py
│   │   ├── windows.py           (todo)
│   │   ├── android.py           (todo)
│   │   ├── ios.py               (todo)
│   │   ├── get-location-mac.swift
│   │   ├── GetLocationMac.app/
├── keystrokes/                  (scaffolding only, not implemented)
│   ├── __init__.py
│   ├── keystrokes.py            >> get_keystrokes()
│   ├── keystroke.txt
│   ├── src/
│   │   ├── mac.py               (todo)
│   │   ├── windows.py           (todo)
│   │   ├── android.py           (todo)
│   │   ├── ios.py               (todo)
