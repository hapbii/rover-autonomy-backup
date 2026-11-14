import hashlib,io,json,pathlib,urllib.request,zipfile
root=pathlib.Path.cwd()
data=json.loads((root/'tools/arduino-data/package_index.json').read_text())
tool=next(s for pkg in data['packages'] if pkg['name']=='arduino' for t in pkg['tools'] if t['name']=='avrdude' and t['version']=='6.3.0-arduino18' for s in t['systems'] if s['host']=='i686-mingw32')
blob=urllib.request.urlopen(tool['url'],timeout=30).read()
assert hashlib.sha256(blob).hexdigest()==tool['checksum'].split(':')[1]
dest=pathlib.Path.home()/'AppData/Local/Temp/rover_avrdude_6_3_official'
dest.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(blob)) as archive:
    for name in archive.namelist():
        assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
    archive.extractall(dest)
print(dest)
print([str(p) for p in dest.rglob('avrdude*')])
