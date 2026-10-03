### source-module functionality (naming/outputs)

sources/
├── sourcename/
│   ├── __init__.py
│   ├── sourcename.py
│   ├── src/
│   │   ├── 
│   │   ├── 

sourcename.py >> contains the get_sourcename() function to collect data

__init__.py >> re-exports get_sourcename() so the main application can import it directly

src/ >> everything else the source needs (platform-specific code, helpers, binaries)

The main application only imports get_sourcename():

    from sources.sourcename import get_sourcename

#### current sources

sources/
├── location/
│   ├── __init__.py
│   ├── location.py              >> get_location()
│   ├── src/
│   │   ├── mac.py
│   │   ├── windows.py           (not implemented)
│   │   ├── get-location-mac.swift
│   │   ├── GetLocationMac.app/
├── keystrokes/                  (not yet structured)
│   ├── keystroke.txt
