



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
│   ├── src/
│   │   ├── mac.py               (todo)
│   │   ├── windows.py           (todo)
│   │   ├── android.py           (todo)
│   │   ├── ios.py               (todo)
├── filetree/
│   ├── __init__.py
│   ├── filetree.py              >> get_filetree()
│   ├── src/
│   │   ├── mac.py
│   │   ├── windows.py           (todo)
│   │   ├── android.py           (todo)
│   │   ├── ios.py               (todo)




# main.py

Runs one thread per source via the `SOURCES` config table, each polling on its
own interval (location every 10s, filetree hourly). A `stop` Event gives clean
Ctrl-C shutdown; a print lock keeps log lines from interleaving. location and
filetree are both live; keystrokes is not yet wired in.
