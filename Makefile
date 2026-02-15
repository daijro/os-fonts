.PHONY: all win11 merge zip clean-temp clean clean-all

all: win11 merge

win11:
	python3 win11/download_utils.py download
	python3 win11/download_utils.py extract

build-locales:
	python3 win11/win11_locales.py
	python3 ubuntu/ubuntu_locales.py

merge: build-locales
	python3 merge.py

zip:
	rm -rf _zip os-fonts.zip
	mkdir -p _zip/fonts _zip/fontconfigs
	cp -r merged/* _zip/fonts/
	cp -r fontconfigs/* _zip/fontconfigs/
	cp font-map.min.json _zip/
	cd _zip && 7z a -tzip -mx=9 ../os-fonts.zip .
	rm -rf _zip

clean-temp:
	python3 win11/download_utils.py clean

clean: clean-temp
	rm -rf merged merge.yml font-map.json font-map.min.json _zip os-fonts.zip

clean-all: clean
	rm -rf win11/fonts win11/fod-mapping.xlsx win11/extraction.json win11/locales.json ubuntu/locales.json
