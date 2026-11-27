"""Small built-in Estonian/English translation catalog for Qeoloog."""


EN = {
    "Litotulp": "Lithology log",
    "Litotulp…": "Lithology log…",
    "Algus (m)": "From (m)",
    "Lõpp (m)": "To (m)",
    "Automaatne": "Automatic",
    "Püstpaigutus": "Portrait",
    "Rõhtpaigutus": "Landscape",
    "Värvid": "Colours",
    "Mustrid": "Patterns",
    "Koostaja": "Prepared by",
    "Lisa gammalogi (CSV)…": "Add gamma log (CSV)…",
    "Impordi mõõteandmed…": "Import measurements…",
    "Exceli näidis…": "Excel example…",
    "Salvesta kaasasoleva Exceli näidisfaili koopia.": "Save a copy of the included Excel example.",
    "Salvesta Exceli näidis": "Save Excel example",
    "Kas asendada olemasolev Exceli fail?": "Replace the existing Excel file?",
    "Exceli näidist ei saanud salvestada": "Could not save the Excel example",
    "Exceli näidis salvestati": "Excel example saved",
    "Eemalda mõõteandmed": "Remove measurements",
    "Salvesta objekti juurde": "Save to local object",
    "Sonditihedus": "Probe density",
    "Proovitihedus": "Sample density",
    "Mag. vastuvõtlikkus": "Magnetic susceptibility",
    "Struktuurielemendid": "Structural elements",
    "Migmatiseerumise aste": "Degree of migmatization",
    "Kuvatakse kivimitulbas, kui Mustrid on sisse lülitatud.": "Drawn in the rock column when Patterns is enabled.",
    "CSV, TSV või XLSX. Failis olevad rajad asendavad eelvaates ainult sama liiki rajad.": "CSV, TSV or XLSX. Only tracks present in the file are replaced in the preview.",
    "Mõõteandmed on eelvaates, kuid objekti juurde salvestamata.": "Measurements are in the preview but not yet saved to the object.",
    "Mõõteandmed kehtivad ainult selles eelvaates.": "Measurements apply to this preview only.",
    "Mõõteandmed on salvestatud kohaliku objekti juurde.": "Measurements are saved to the local object.",
    "Vali mõõteandmete fail. Excelis kasuta lehte „Mõõteandmed”.": "Choose a measurement file. In Excel use a sheet named “Mõõteandmed” or “Measurements”.",
    "Mõõteandmete import ebaõnnestus": "Could not import measurements",
    "Mõõteandmeid ei saanud salvestada": "Could not save measurements",
    "Tööruum on vahetunud. Ava litotulp uuesti.": "The workspace changed. Reopen the lithology log.",
    "Objekt on vahepeal muutunud. Ava litotulp uuesti; salvestatud andmeid ei kirjutatud üle.": "The object changed. Reopen the lithology log; saved data was not overwritten.",
    "Eemalda gammalogi": "Remove gamma log",
    "Gammalogi mõõtühik, näiteks API, kui see on failis kasutatud ühik.": "Gamma log unit, such as API if that is the unit used in the file.",
    "Eelmine leht": "Previous page",
    "Järgmine leht": "Next page",
    "Ekspordi PDF…": "Export PDF…",
    "Ekspordi SVG…": "Export SVG…",
    "Gammalogi lugemine ebaõnnestus": "Could not read the gamma log",
    "Lõppsügavus peab olema algsügavusest suurem.": "The bottom depth must be below the top depth.",
    "Litotulpa ei saanud koostada": "Could not generate the lithology log",
    "Litotulpa ei saanud salvestada": "Could not save the lithology log",
    "Litotulp salvestati": "Lithology log saved",
    "Salvesta litotulp": "Save lithology log",
    "Gammalogi": "Gamma log",
    "Trükimõõtkava": "Print scale",
    "Prooviseeriad": "Sample series",
    "Prooviseosed": "Sample links",
    "Analüüside viited": "Analysis references",
    "Analüüsitulemused": "Analysis results",
    "Vali koos ETL6 (objektid), ETL10 (geoloogia), ETL7 (proovid) ja/või ETL8 (analüüsid). ETL7/8 saab lisada ka olemasolevatele kohalikele objektidele, kui ID-d kattuvad üheselt.": "Choose ETL6 (objects), ETL10 (geology), ETL7 (samples) and/or ETL8 (analyses) together. ETL7/8 can also be added to existing local objects when their IDs match unambiguously.",
    "Laboriandmete täiendused olemasolevatele objektidele": "Laboratory additions to existing objects",
    "Kohalike andmete ETL-eksport": "Local data ETL export",
    "ETL6/10: objektid ja geoloogia. Lisa soovi korral ETL7/8 proovid ja analüüsid. Väljundit ei kinnitata EGT-laaduris.": "ETL6/10: objects and geology. Include ETL7/8 samples and analyses if needed. The output is not certified by the EGT loader.",
    "Lisa proovid ja analüüsid (ETL7/ETL8)": "Include samples and analyses (ETL7/ETL8)",
    "Kohalikud andmed": "Local data",
    "Kohalik": "Local",
    "Originaal": "Original",
    "Originaal (salvestatud)": "Original (captured)",
    "Salvestatud originaal": "Captured original",
    "Kopeeri kohalikuks": "Copy to local workspace",
    "Muuda kohalikku objekti": "Edit local object",
    "Impordi": "Import",
    "Vali ETL-failid…": "Choose ETL files…",
    "ETL6 (.xlsx) sisaldab objekte. Geoloogiliste üksuste ja seotud ridade jaoks vali koos sellega ETL10 (.xlsx). Imporditakse ainult kohalikku tööruumi.": "ETL6 (.xlsx) contains objects. For geological units and child rows, also select ETL10 (.xlsx). Import only writes to the local workspace.",
    "Salvesta tööruumi": "Save to workspace",
    "Vali failid eelvaateks.": "Choose files to preview.",
    "Salvestamiseks loo või ava tööruum paanis Kohalikud andmed.": "To save, create or open a workspace in Local data.",
    "Sidumata ridu": "Unlinked rows",
    "Sidumata read tuleb failis parandada. Import ei jäta ridu vaikides välja.": "Correct the unlinked rows in the workbook. Import will not silently omit them.",
    "Import ebaõnnestus": "Import failed",
    "Imporditi kohalikke objekte": "Imported local objects",
    "Kohalikud andmed: ETL6 ja ETL10": "Local data: ETL6 and ETL10",
    "Väljund on ETL6/ETL10 kujul, kuid seda ei laadita andmebaasi ega kinnitata EGT-laaduris.": "The result uses the ETL6/ETL10 layout. It is not uploaded to a database or verified by the EGT loader.",
    "Vali objektid ja ekspordi Excelisse…": "Select objects and export to Excel…",
    "Aktiivses tööruumis pole kohalikke objekte.": "There are no local objects in the active workspace.",
    "Vali ETL-ekspordi kaust": "Choose the ETL export folder",
    "Eksporditud failid": "Exported files",
    "Kontrolli ETL-eksporti": "Review ETL export",
    "Kontrolli valikut": "Check selection",
    "Kontrollitakse tööruumi salvestatud andmeid.": "The check uses data saved in the workspace.",
    "Kontrollitud objekte: {count}": "Objects checked: {count}",
    "Paranda vead või eemalda vigased objektid ekspordivalikust. Faile ei looda.": "Fix the errors or remove the affected objects from the selection. No files are created.",
    "Hoiatused ei muuda andmeid. Selle valiku saad eksportida mustandina.": "Warnings do not change the data. You can export this selection as a draft.",
    "Qeoloogi kontroll ei leidnud probleeme. See ei kinnita faili vastuvõttu EGT-laaduris.": "Qeoloog found no issues. This does not certify acceptance by the EGT loader.",
    "Vead": "Errors",
    "Hoiatused": "Warnings",
    "Tagasi objektide valikusse": "Back to object selection",
    "Ekspordi mustand…": "Export draft…",
    "Vali ekspordikaust…": "Choose export folder…",
    "Puuduvad või kontrollimata väärtused jäävad muutmata. Soovi korral salvesta pakett mustandina, mitte laadimiseks kinnitatud failina.": "Missing or unverified values are left as-is. You may save a draft package; it is not verified for database loading.",
    "Ekspordi mustand": "Export draft",
    "Loo või ava tööruum. Seejärel saad valitud objekti kohalikuks kopeerida.": "Create or open a workspace before copying the selected object locally.",
    "Oota, kuni lähteobjekti läbilõige on laaditud.": "Wait for the source geological log to load.",
    "Lähteobjekti läbilõige ei laadinud. Kas kopeerida ainult üldandmed?": "Could not load the source geological log. Copy just the general data?",
    "Lähteobjekti vaates pole geoloogilisi üksusi. Kas kopeerida ainult üldandmed?": "There are no geological units in the source view. Copy just the general data?",
    "Vahekihid": "Interbeds",
    "Mineraalid": "Minerals",
    "Fossiilid ja detriit": "Fossils and detritus",
    "Nähtused": "Features",
    "Muuda joonisel": "Edit drawing",
    "Paljandi redigeerimine": "Edit outcrop",
    "Vali ja lohista": "Select and drag",
    "Biotsooni leiupunkt": "Biozone occurrence",
    "Biotsoonide leiupunktid": "Biozone occurrence points",
    "Tõlgendatud biotsoonide ulatus": "Interpreted biozone ranges",
    "Takson": "Taxon",
    "Biotsoon": "Biozone",
    "Vaatlus": "Observation",
    "Paljandi vaatlused": "Outcrop observations",
    "Varjatud vahemik": "Obscured interval",
    "Varjatud vahemikud": "Obscured intervals",
    "Varingurusuga kaetud": "Covered by rockfall debris",
    "Varjatud": "Obscured",
    "Vaatlemata": "Not observed",
    "Varingurusu": "Rockfall debris",
    "Varingurusu ala": "Rockfall debris area",
    "Seinaprofiil": "Wall profile",
    "Seinaprofiil (m)": "Wall profile (m)",
    "Seinaprofiil (skeem)": "Wall profile (schematic)",
    "Eend": "Protrusion",
    "Süvend": "Recess",
    "Mõõdetud": "Measured",
    "Skemaatiline": "Schematic",
    "Asend": "Position",
    "Asend (m)": "Position (m)",
    "Nihe": "Offset",
    "Tunnus": "Feature",
    "Foto": "Photo",
    "Võta tagasi": "Undo",
    "Tee uuesti": "Redo",
    "Salvesta paljand": "Save outcrop",
    "Vali objektide tabelist kuvatav kohalik paljand.": "Select a visible local outcrop in the object table.",
    "Muuda kirjet…": "Edit record…",
    "Eemalda kirje": "Remove record",
    "Klõpsa seinaprofiili rajal; Enter lõpetab, Esc katkestab.": "Click in the wall-profile track; Enter finishes, Esc cancels.",
    "Lohista piire, punkte, tippe või silte; paremklõps avab kirje.": "Drag boundaries, points, vertices or labels; right-click for record actions.",
    "Lohista üle varjatud vahemiku.": "Drag across the obscured interval.",
    "Klõpsa paljandi tulbal soovitud kõrgusel.": "Click the outcrop log at the desired height.",
    "Lisa kujule rohkem tippe.": "Add more vertices to the shape.",
    "Joonistustoiming katkestatud.": "Drawing gesture cancelled.",
    "Kirje väärtused ei sobi.": "Invalid record values.",
    "Vahemiku algus (m)": "Interval start (m)",
    "Vahemiku lõpp (m)": "Interval end (m)",
    "Vali foto või manus…": "Choose photo or attachment…",
    "Tipud: nihe; asend (üks paar real)": "Vertices: offset; position (one pair per line)",
    "Samu kõrgusi võib kasutada mitu korda. Jäta tippude järjekord alles.": "Multiple vertices may have the same height. Keep vertices in draw order.",
    "Sisesta igale reale kaks arvu: nihe; asend.": "Enter two numbers on each line: offset; position.",
    "Kas loobuda salvestamata joonise muudatustest?": "Discard unsaved drawing changes?",
    "Salvesta või katkesta esmalt paljandi redigeerimine.": "Save or cancel the outcrop edit first.",
    "Sisesta lõplik arv vahemikus ±1 000 000; kõrgus ei tohi olla negatiivne.": "Enter a finite number within ±1,000,000; height must not be negative.",
    "Vaatlusandmed peavad olema kirje kujul.": "Observation data must be a record.",
    "Tundmatu paljandiraja tüüp.": "Unknown outcrop track type.",
    "Tundmatu paljandikirje tüüp.": "Unknown outcrop record kind.",
    "Varjatud vahemik peab olema nullist pikem.": "The obscured interval must have nonzero length.",
    "Paljandi kuju võib sisaldada kuni 2000 tippu.": "An outcrop shape can contain up to 2,000 vertices.",
    "Igal tipul peab olema nihe ja kõrgus.": "Each vertex needs an offset and height.",
    "Varingurusu ala vajab vähemalt kolme tippu ja pindala.": "Rockfall debris needs a polygon with at least three vertices and nonzero area.",
    "Seinaprofiil vajab vähemalt kahte eri tippu.": "A wall profile needs at least two distinct vertices.",
    "Tööruum": "Workspace",
    "Loo töökaust…": "Create workspace…",
    "Ava olemasolev töökaust…": "Open existing workspace…",
    "Ava töökaust Finderis / failihalduris": "Show workspace in file manager",
    "Varundamise seaded…": "Backup settings…",
    "Tee varukoopia kohe": "Back up now",
    "Taasta koopiast…": "Restore from backup…",
    "Uus nimeline läbilõige…": "New named section…",
    "Tee läbilõikest koopia…": "Duplicate section…",
    "Lisa korrelatsioon…": "Add correlation…",
    "Halda korrelatsioone…": "Manage correlations…",
    "Joonda valitud tulp…": "Align selected log…",
    "Lähtesta joondus": "Reset alignment",
    "Tulbad": "Logs",
    "Lisa kohalik tulp või paljand…": "Add local log or outcrop…",
    "Lisa tulp tööruumist…": "Add log from workspace…",
    "Redigeeri valitud tulpa…": "Edit selected log…",
    "Ava valitud tulba algkirje": "Open source record",
    "Mine valitud tulba asukohta": "Go to selected log location",
    "Ava kohalik manus…": "Open local attachment…",
    "Kujundus": "Appearance",
    "StrataPy-laadne": "StrataPy-inspired",
    "Kohanda joonist…": "Customize drawing…",
    "Alapealkiri": "Subtitle",
    "Tulba laius (px)": "Log width (px)",
    "Säilita EGT indeksivärvid": "Keep EGT index colors",
    "Kuva legend": "Show legend",
    "Radade järjekord": "Track order",
    "Kopeeri kujundus teisest läbilõikest…": "Copy appearance from another section…",
    "Katkesta isotoobikõver, kui vahe ületab (m; 0 = väljas)": "Break isotope curve across gaps longer than (m; 0 = off)",
    "Läbilõigete tööruumi toiming ebaõnnestus.": "Section workspace operation failed.",
    "Töökaust": "Workspace folder",
    "Projekti läbilõige": "Project section",
    "Töökaust pole kättesaadav. Ava olemasolev töökaust või taasta varukoopiast.": "Workspace unavailable. Open an existing workspace or restore from backup.",
    "Nimeliste läbilõigete ja kohalike tulpade jaoks vali töökaust.": "Choose a workspace for named sections and local logs.",
    "Vali esmalt töökaust.": "Choose a workspace first.",
    "Vali varukoopiate kaust": "Choose backup folder",
    "Varukoopiad peavad asuma väljaspool töökausta.": "Backups must be outside the workspace folder.",
    "Varunda automaatselt pärast salvestamist (säilita viimased 10 koopiat)?": "Back up automatically after saving (keep the latest 10 copies)?",
    "Varukoopia": "Backup",
    "Vali varukoopia kaust": "Choose the backup to restore",
    "Vali taastatud töökausta ülemkaust": "Choose where to create the restored workspace",
    "Taastatud": "Restored",
    "Toetatud allikad: EGT, SARV ja VEKA.": "Supported sources: EGT, SARV and VEKA.",
    "Tööruumis pole veel kohalikke tulpi.": "The workspace has no local logs yet.",
    "Tulp": "Log",
    "Algkirje ei ole avatud kihis": "Source record is not in a loaded layer",
    "Tulbal puudub algkirje viide.": "This log has no source reference.",
    "Märgi paljandi joon kaardil (Enter lõpetab, Esc katkestab).": "Draw the outcrop trace (Enter to finish, Esc to cancel).",
    "Vali tulba asukoht kaardilt (Esc katkestab).": "Pick the log location on the map (Esc to cancel).",
    "Korrelatsiooniks on vaja kahe tulba piire või mõõtepunkte.": "Correlation requires boundaries or measurements on two logs.",
    "Oletuslik ühendus": "Inferred correlation",
    "Isotoobid": "Isotopes",
    "Biotsoonid": "Biozones",
    "Lademed": "Regional stages",
    "Korrelatsioonid": "Correlations",
    "Korrelatsioon": "Correlation",
    "Suhteline kõrgus / sügavus": "Relative height / depth",
    "Määra vähemalt ühe tulba korrelatsiooni nulltase.": "Set a correlation datum for at least one log.",
    "Lisa läbilõikele vähemalt üks objekt.": "Add at least one object to the section.",
    "Mõõdetud kõrgus / −sügavus lähtekohast (m)": "Measured height / −depth from log origin (m)",
    "Korrelatsiooni nulltase (m)": "Relative to correlation datum (m)",
    "Kinnitatud seos": "Confirmed correlation",
    "Oletuslik seos": "Inferred correlation",
    "Terasuurus (mm)": "Grain size (mm)",
    "Karbonaatkivim": "Carbonate rock",
    "Liiv / liivakivi": "Sand / sandstone",
    "Savi / aleuriit": "Clay / silt",
    "Kruus / konglomeraat": "Gravel / conglomerate",
    "Orgaaniline sete": "Organic deposit",
    "Muu / määramata litoloogia": "Other / unknown lithology",
    "Isotoop": "Isotope",
    "Võrdlusskaala": "Reference scale",
    "Mõõtemääramatus": "Measurement uncertainty",
    "Sügavus / kõrgus (m)": "Depth / height (m)",
    "Skeem": "Scheme",
    "Proovi viide": "Sample reference",
    "Allika viide": "Source reference",
    "Ava mõõtmise viide": "Open measurement reference",
    "Algus": "Start",
    "Lõpp": "End",
    "Fondi teenus muutus päringu ajal. Proovi uuesti.": "The archive service changed during the request. Please try again.",
    "Aruande ala": "Report area",
    "Fondi aruande ala": "Archive report area",
    "PA filter": "BH filter",
    "Kuva või eemalda selle fondiaruande ruumikuju. Filter töötab sellest sõltumatult.": "Show or remove this report's outline. The filter works independently.",
    "Kuva ainult fondiaruande ala sisse jäävad avalikud EGT puuraugud. Teised filtrid säilivad.": "Show only public EGT boreholes within this report's area. Other filters are preserved.",
    "Eemalda fondiala filter; säilita teised filtrid ja ruumikujud.": "Clear the report-area filter; preserve other filters and outlines.",
    "Fondi uuringualade teenus puudub seadetest.": "The archive survey-area service is missing from settings.",
    "Fondi ruumikuju vastus on vigane.": "Invalid archive geometry response.",
    "Fondi teenus kordas objekte; ruumikuju on poolik.": "The archive service repeated features; the geometry is incomplete.",
    "Fondi ruumikuju puudub või ei ole pindobjekt.": "The archive geometry is missing or is not a polygon.",
    "Fondi ruumikuju ei saa kasutada.": "The archive geometry cannot be used.",
    "Fondi ruumikuju on poolik; filtrit ei rakendatud.": "The archive geometry is incomplete; the filter was not applied.",
    "Sellel fondiaruandel puudub avalik ruumikuju.": "This archive report has no public spatial outline.",
    "Fondi ruumikujude ühendamine ebaõnnestus.": "Could not combine the report's spatial outlines.",
    "Fondi ruumikuju kihi laadimine ebaõnnestus.": "Could not load the archive outline layer.",
    "Vali kirje": "Select a record",
    "Asukohakonflikt — kinnita seos käsitsi": "Location conflict — confirm the link manually",
    "Qeoloog": "Qeoloog",
    "Lisakihid": "Additional layers",
    "Aluskaardid": "Base maps",
    "Geoloogia": "Geology",
    "Läti": "Latvia",
    "Puuraugud": "Boreholes",
    "Põhjavesi": "Groundwater",
    "Maavarad": "Mineral resources",
    "Läti LVĢMC": "Latvia LVĢMC",
    "Läti geoloogilised puuraugud": "Latvian geological boreholes",
    "Läti geoloogiline puurauk": "Latvian geological borehole",
    "Läti objekt": "Latvian feature",
    "LVĢMC kiht": "LVĢMC layer",
    "Klõpsa toetatud kaardiobjektil ja ava selle andmed": (
        "Click a supported map feature to open its data"
    ),
    "MapServeri kihtide lugemine ebaõnnestus": (
        "Could not read MapServer layers"
    ),
    "Teenuse CRS": "Service CRS",
    "Alammenüü": "Submenu",
    "Uuringud ja maavarad": "Surveys and mineral resources",
    "Maavarade registri objekt": "Mineral-register object",
    "Liiv": "Sand",
    "Kruus": "Gravel",
    "Turvas": "Peat",
    "Lubjakivi": "Limestone",
    "Dolokivi": "Dolostone",
    "Savi": "Clay",
    "Põlevkivi": "Oil shale",
    "Fosforiit": "Phosphorite",
    "Meremuda": "Marine mud",
    "Järvemuda": "Lake mud",
    "Järvelubi": "Lake marl",
    "Aluskorra ehituskivi": "Crystalline basement construction stone",
    "Mitu maavara": "Multiple mineral resources",
    "Abikihid": "Reference layers",
    "Kihid": "Layers",
    "Kihikataloog": "Layer catalogue",
    "Otsi koodi, nime, teenuse või URL-i järgi": (
        "Search by code, name, service or URL"
    ),
    "Kõik teenused": "All services",
    "Kõik rühmad": "All groups",
    "Kõik olekud": "All states",
    "Lubatud": "Enabled",
    "MaRu puursüdamike andmekogu": "MaRu historical drill-core database",
    "Kohalikku MaRu otsinguindeksit pole veel laaditud.": (
        "The local MaRu search index has not been downloaded yet."
    ),
    "Laadi / uuenda MaRu andmekogu": "Download / update MaRu database",
    "MaRu andmekogu laadimine ebaõnnestus": (
        "Could not load the MaRu database"
    ),
    "MaRu andmebaasi kohalik koopia uuendati.": (
        "The local MaRu database copy was updated."
    ),
    "MaRu andmebaasi uuendamine ebaõnnestus": (
        "Could not update the MaRu database"
    ),
    "MaRu puursüdamikud": "MaRu drill cores",
    "EGT, SARV, MaRu ja VEKA": "EGS, SARV, MaRu and VEKA",
    "Otsing ja filtrid": "Search and filters",
    "Rakenda läbilõikele": "Add to cross-section",
    "Lisa tulemuste tabelis valitud puuraugud või puurkaevud koondläbilõikele.": (
        "Add the boreholes or wells selected in the results table to the cross-section."
    ),
    "Vali esmalt tulemuste tabelist vähemalt üks rida.": (
        "Select at least one row in the results table first."
    ),
    "Läbilõikele lisati {count} objekti.": (
        "Added {count} objects to the cross-section."
    ),
    "MaRu tunnused": "MaRu identifiers",
    "MaRu ID": "MaRu ID",
    "GB ID": "GB ID",
    "Fond": "Archive fund",
    "MaRu proovid": "MaRu samples",
    "Kivim": "Rock",
    "Hoiukoht": "Storage location",
    "Kast": "Box",
    "Koguja": "Collector",
    "Kogumise aasta": "Collection year",
    "MaRu seotud andmed": "Related MaRu data",
    "EGT seos": "EGS link",
    "SARV seos": "SARV link",
    "Kastifoto": "Core-box photo",
    "Proovifoto": "Sample photo",
    "Õhik": "Thin section",
    "Keemiline analüüs": "Chemical analysis",
    "Mineraloogia": "Mineralogy",
    "Granulomeetria": "Granulometry",
    "Spektraalanalüüs": "Spectral analysis",
    "Karbonaatsus": "Carbonate analysis",
    "MaRu filtrid rakenduvad Otsingu vaates siis, kui allikaks on valitud MaRu või kõigi allikate otsing.": (
        "MaRu filters apply in Search when the source is MaRu or all sources."
    ),
    "EGT ma_orig_id kattub": "EGS ma_orig_id matches",
    "Nimetus": "Label",
    "Abs Z": "Absolute Z",
    "Kuva MaRu kastifotod ka manustes": (
        "Also show MaRu core-box photos in attachments"
    ),
    "Ekspordi SARV ja MaRu seosed…": "Export SARV and MaRu links…",
    "Ekspordi SARV ja MaRu seosed": "Export SARV and MaRu links",
    "MaRu seose haldus": "MaRu link management",
    "MaRu objekt pole seotud": "No MaRu object is linked",
    "Määra MaRu seos": "Set MaRu link",
    "MaRu puursüdamiku ID": "MaRu drill-core ID",
    "Muuda MaRu seost": "Change MaRu link",
    "Lisa MaRu seos": "Add MaRu link",
    "Taasta EGT MaRu seos": "Restore the EGS MaRu link",
    "Vigane Maa-ameti ID seos": "Incorrect Land Board ID link",
    "Kinnitatud MaRu vaste": "Confirmed MaRu match",
    "Võimalik MaRu vaste": "Possible MaRu match",
    "MaRu vaste salvestati kohalikult.": "The MaRu match was saved locally.",
    "EGT MaRu seos taastati.": "The EGS MaRu link was restored.",
    "Sellise ID-ga MaRu puursüdamikku ei leitud.": (
        "No MaRu drill core with this ID was found."
    ),
    "MaRu puursüdamiku kirjet ei leitud.": (
        "The MaRu drill-core record was not found."
    ),
    "MaRu üldandmed": "MaRu general data",
    "MaRu geoloogiline kirjeldus": "MaRu geological description",
    "puursüdamikku": "drill cores",
    "allikas": "source",
    "uuendatud": "updated",
    "Lisa, muuda või eemalda WMS/WFS/ArcGIS/SARV/VEKA kihte": (
        "Add, edit or remove WMS/WFS/ArcGIS/SARV/VEKA layers"
    ),
    "EGT Portal": "EGS Portal",
    "EGT Portali kihid": "EGS Portal layers",
    "Värskenda Portali kihte": "Refresh Portal layers",
    "Logi esmalt EGT Portalisse": "Sign in to the EGS Portal first",
    "Portali teenuseid laaditakse…": "Loading Portal services…",
    "Portali kataloogis pole teenuseid": "The Portal catalog has no services",
    "Minuga jagatud": "Shared with me",
    "Organisatsioon": "Organisation",
    "Avalikud": "Public",
    "Põhikaust": "Root folder",
    "Ava teenuse kihtide lugemiseks": "Open to read service layers",
    "Kihte laaditakse…": "Loading layers…",
    "Kihte ei leitud": "No layers found",
    "Teenuse kihtide laadimine ebaõnnestus": "Could not load service layers",
    "EGT Portali kataloog": "EGS Portal catalog",
    "teenust": "services",
    "Portali kataloogi laadimine ebaõnnestus": (
        "Could not load the Portal catalog"
    ),
    "Faktika töökiht": "Faktika working layer",
    "Faktika testserver": "Faktika test server",
    "Kuva Faktika testserver EGT menüüs": (
        "Show the Faktika test server in the EGT menu"
    ),
    "Testserver on tootmisandmetest eraldatud ja ilmub EGT menüüsse ainult selle valiku sisselülitamisel.": (
        "The test server is separate from production and appears in the EGT "
        "menu only after this option is enabled."
    ),
    "Testserveri andmed; muudatused ei lähe tootmiskeskkonda": (
        "Test-server data; edits are not sent to production"
    ),
    "Sisemised puuraugud, vaatluspunktid ja seotud tabelid": (
        "Internal boreholes, observation points and related tables"
    ),
    "Faktika töökiht ja seotud tabelid lisati.": (
        "Faktika working layer and related tables were added."
    ),
    "Faktika töökiht eemaldati.": "Faktika working layer was removed.",
    "Seotud tabelid": "Related tables",
    "Puurauk": "Borehole",
    "Vaatluspunkt": "Observation point",
    "Vaatluspunkt merel": "Offshore observation point",
    "Pinnakate": "Cover",
    "Aluspõhi": "Bedrock",
    "Aluskord": "Basement",
    "Muu / teadmata": "Other / unknown",
    "Lisa objekt": "Add object",
    "Redigeeri": "Edit",
    "Detailvaade": "Detailed view",
    "Ava täidetud väljad ja seotud tabelid eraldi kirjutuskaitstud aknas": (
        "Open populated fields and related tables in a separate read-only window"
    ),
    "Kirjutuskaitstud vaade. Algväärtus näitab lähteandmetes olevat koodi, kui kuvatav väärtus on domeenisildiks tõlgitud.": (
        "Read-only view. Original value shows the source code when the displayed value has been decoded to a domain label."
    ),
    "Kirjutuskaitstud vaade. Algväärtus näitab lähteandmetes olevat koodi, kui kuvatav väärtus on domeenisildiks tõlgitud. Kirje kõigi täidetud lähteväljade nägemiseks tee tabelireal topeltklõps.": (
        "Read-only view. Original value shows the source code when the displayed value has been decoded to a domain label. Double-click a table row to inspect all populated source fields for that record."
    ),
    "Otsi aktiivsest tabelist": "Search active table",
    "Sisesta otsingutekst…": "Enter search text…",
    "Kopeeri valitud read": "Copy selected rows",
    "Kopeeri aktiivne tabel": "Copy active table",
    "Kopeeri kõik": "Copy all",
    "Sulge": "Close",
    "Algväärtus": "Original value",
    "Tehniline väli": "Technical field",
    "Täidetud väljad": "Populated fields",
    "Genees": "Genesis",
    "Kuvatud read: {visible}/{total}": "Visible rows: {visible}/{total}",
    "Andmed kopeeriti lõikelauale.": "Data copied to the clipboard.",
    "kirjutuskaitstud": "read-only",
    "Lisa Faktika objekt": "Add Faktika object",
    "Kas valida uue objekti asukoht kaardilt?\nJah: klõpsa kaardil; Ei: kasuta kaardi keskpunkti.": (
        "Choose the new object's location on the map?\n"
        "Yes: click the map; No: use the map centre."
    ),
    "Klõpsa kaardil uue Faktika objekti asukohas. Esc tühistab.": (
        "Click the location of the new Faktika object. Esc cancels."
    ),
    "Kaardilt asukoha valimine pole saadaval.": (
        "Map location picking is unavailable."
    ),
    "Redigeeri Faktika objekti": "Edit Faktika object",
    "Objekti tüüp": "Object type",
    "Sihtkeskkond": "Target environment",
    "Koordinaadid (L-EST97)": "Coordinates (L-EST97)",
    "Asukoha kõrguskontroll": "Elevation-based location check",
    "Kõrgusraster": "Elevation raster",
    "Vali rasterkiht": "Select raster layer",
    "Värskenda rasterkihte": "Refresh raster layers",
    "Kõrgussüsteem": "Height datum",
    "Objekti Z": "Object Z",
    "Raster": "Raster",
    "Teadmata": "Unknown",
    "Ei kohaldu": "Not applicable",
    "EUREF-EST97 ellipsoidaalne": "EUREF-EST97 ellipsoidal",
    "Sobivusvahemik": "Matching tolerance",
    "Täpsemad": "Advanced",
    "Kõrguskanal": "Elevation band",
    "Vali raster ning objekti kõrgussüsteem. Z-väärtust ei muudeta.": (
        "Select a raster and the object's height datum. Z is never changed."
    ),
    "Kontrolli praegust asukohta": "Check current location",
    "Kuva sobivusala": "Show matching area",
    "Peida sobivusala": "Hide matching area",
    "Vali kandidaat kaardilt": "Pick candidate on map",
    "Määra kandidaadi X/Y": "Use candidate X/Y",
    "Klõpsa kaardil kõrguse järgi kontrollitavas kandidaatkohas. Esc tühistab.": (
        "Click a candidate location to check against the elevation. Esc cancels."
    ),
    "Kõrgus või koordinaadid ei ole korrektsed.": (
        "The height or coordinates are invalid."
    ),
    "Kõrgussüsteem on teadmata; väärtust ei teisendatud.": (
        "The height datum is unknown; the value was not converted."
    ),
    "Kõrgussüsteemide teisendus pole toetatud.": (
        "This height-datum conversion is unsupported."
    ),
    "Kõrguse sobivusala": "Elevation matching area",
    "Vali sobiv rasterkiht.": "Select a suitable raster layer.",
    "Rasterkihi koopiat ei saanud luua.": "Could not clone the raster layer.",
    "Kõrgust teisendatakse…": "Converting height…",
    "Võrdluskõrgus": "Comparison elevation",
    "Kõrguse teisendamine ebaõnnestus": "Height conversion failed",
    "DEM mediaan": "DEM median",
    "Selles punktis puudub rasterväärtus.": (
        "The raster has no value at this location."
    ),
    "Sobivusala kuvab ainult sihtkõrguse vahemikku.": (
        "The matching area shows only the target elevation range."
    ),
    "Kandidaat": "Candidate",
    "Kandidaadi X/Y lisati vormile. Z jäi muutmata; muudatus salvestub alles koos kogu objektiga.": (
        "The candidate X/Y was copied to the form. Z was unchanged; the edit "
        "is saved only with the full object."
    ),
    "Geoloogilised üksused": "Geological units",
    "Manuse märksõnad": "Attachment keywords",
    "Manuse märksõna": "Attachment keyword",
    "Juurdepääsu alus": "Access basis",
    "Juurdepääs": "Access",
    "Isik": "Person",
    "Isikud": "Persons",
    "sisemine kirje": "internal record",
    "uus objekt": "new object",
    "Kontrolli ja salvesta": "Validate and save",
    "Lisa": "Add",
    "Muuda": "Edit",
    "Kustuta": "Delete",
    "Lisa alla": "Add below",
    "Poolita": "Split",
    "Dubleeri": "Duplicate",
    "Täpsemad väljad…": "Advanced fields…",
    "Geoloogilise üksuse täpsemad andmed": (
        "Advanced geological-unit fields"
    ),
    "Z1 abs, Z2 abs ja paksus arvutatakse automaatselt objekti Z ning suhteliste sügavuste põhjal. Ridade järjekorra määravad sügavused.": (
        "Absolute Z1/Z2 and thickness are calculated automatically from the "
        "object Z and relative depths. Depths determine row order."
    ),
    "Andmed vajavad parandamist": "The data need correction",
    "Kontrolli hoiatusi": "Review warnings",
    "Kas salvestada siiski?": "Save anyway?",
    "Muudatusi salvestatakse…": "Saving changes…",
    "Muudatused salvestati.": "Changes were saved.",
    "Salvestamine ebaõnnestus": "Save failed",
    "Faktika: otsin vastet…": "Faktika: finding a match…",
    "Faktika ei ole redigeerimiseks saadaval": (
        "Faktika is not available for editing"
    ),
    "Faktika andmete laadimine ebaõnnestus": "Could not load Faktika data",
    "Avalik kirje · Faktika vaste puudub": (
        "Public record · no Faktika match"
    ),
    "Faktika konflikt · globalid ei kattu": (
        "Faktika conflict · GlobalID differs"
    ),
    "Faktika · sisemine ja avalik kirje kattuvad": (
        "Faktika · internal and public records match"
    ),
    "Faktika · sisemine kirje": "Faktika · internal record",
    "Sellel objektil puudub redigeeritav Faktika vaste.": (
        "This object has no editable Faktika match."
    ),
    "Faktika teenus ei anna sellele kasutajale vajalikku redigeerimisõigust.": (
        "The Faktika service does not grant this user the required edit permission."
    ),
    "Faktika muudatused salvestati Portalisse.": (
        "Faktika changes were saved to the Portal."
    ),
    "Kirjet on Portalis vahepeal muudetud. Ava objekt uuesti, et vältida teise kasutaja muudatuste ülekirjutamist.": (
        "The Portal record changed while it was open. Reopen it to avoid "
        "overwriting another user's changes."
    ),
    "Ühenda EGT Portaliga ühe nupuvajutusega. Esimesel korral küsib Qeoloog ainult sisejuhendis olevaid Client ID ja Client secret väärtusi; edaspidi kasutatakse QGIS-i turvalist autentimishoidlat.": (
        "Connect to the EGS Portal with one button. On first use Qeoloog asks "
        "only for the Client ID and Client secret from the internal guide; "
        "QGIS' secure authentication store is used afterwards."
    ),
    "Ühenda EGT Portaliga": "Connect to EGS Portal",
    "Täpsemad sätted": "Advanced settings",
    "Seadista uus ühendus…": "Set up a new connection…",
    "EGT Portaliga ühendamine": "Connect to EGS Portal",
    "Sisesta üks kord EGT sisejuhendis näidatud Client ID ja Client secret. Kõik muud OAuthi seaded täidab Qeoloog automaatselt ning väärtused salvestatakse QGIS-i krüpteeritud autentimishoidlasse.": (
        "Enter the Client ID and Client secret shown in the internal EGS guide "
        "once. Qeoloog fills in every other OAuth setting automatically and "
        "stores the values in QGIS' encrypted authentication store."
    ),
    "Loo ühendus ja logi sisse": "Create connection and sign in",
    "Client ID and Client secret are required.": (
        "Client ID and Client secret are required."
    ),
    "Seadista esmalt EGT Portali turvaline ühendus.": (
        "First set up the secure EGS Portal connection."
    ),
    "QGIS-i autentimishoidla ei ole selles profiilis kasutatav.": (
        "The QGIS authentication store is not available in this profile."
    ),
    "QGIS-i autentimishoidla tuleb esmalt avada.": (
        "The QGIS authentication store must be unlocked first."
    ),
    "EGT Portali autentimise salvestamine ebaõnnestus": (
        "Could not save EGS Portal authentication"
    ),
    "EGT Portali autentimise salvestamine ebaõnnestus.": (
        "Could not save EGS Portal authentication."
    ),
    "EGT Portali turvaline ühendus loodi QGIS-i autentimishoidlas.": (
        "The secure EGS Portal connection was created in the QGIS "
        "authentication store."
    ),
    "Vali QGIS-i autentimisandmebaasist juhendi järgi loodud EGT Portali OAuth2 konfiguratsioon. Qeoloog salvestab ainult selle tunnuse, mitte kasutaja paroole ega tokeneid.": (
        "Select the EGS Portal OAuth2 configuration created in the QGIS "
        "authentication database according to the organisation's guide. "
        "Qeoloog stores only its identifier, never user passwords or tokens."
    ),
    "Autentimiseta (avalik kiht)": "No authentication (public layer)",
    "Puuduv autentimiskonfiguratsioon": "Missing authentication configuration",
    "Värskenda": "Refresh",
    "Logi sisse / kontrolli": "Sign in / verify",
    "Ava QGIS-i autentimisseaded…": "Open QGIS authentication settings…",
    "EGT Portali ühendust pole kontrollitud.": (
        "The EGS Portal connection has not been verified."
    ),
    "EGT Portalisse logitakse sisse…": "Signing in to the EGS Portal…",
    "EGT Portali kasutaja": "EGS Portal user",
    "EGT Portali sisselogimine ebaõnnestus": "EGS Portal sign-in failed",
    "Vali esmalt juhendi järgi loodud EGT Portali autentimine.": (
        "First select the EGS Portal authentication configuration created "
        "according to the guide."
    ),
    "Vali Kihid-paanil EGT Portali autentimine.": (
        "Select EGS Portal authentication on the Layers page."
    ),
    "Kasuta valitud EGT Portali autentimist": (
        "Use the selected EGS Portal authentication"
    ),
    "Autentimine": "Authentication",
    "FeatureServeri kihtide lugemine ebaõnnestus": (
        "Could not read FeatureServer layers"
    ),
    "Aktiivse Portali kihi redigeerimine": (
        "Edit active Portal layer"
    ),
    "Alusta redigeerimist": "Start editing",
    "Salvesta Portalisse": "Save to Portal",
    "Loobu muudatustest": "Discard changes",
    "Lubatud toimingud": "Allowed operations",
    "Kiht on selle Portali kasutaja jaoks kirjutuskaitstud.": (
        "The layer is read-only for this Portal user."
    ),
    "Portali kiht on redigeeritav": "The Portal layer is editable",
    "lisamine": "add",
    "muutmine": "update",
    "kustutamine": "delete",
    "Aktiivne Portali kiht ei luba selle kasutajaga redigeerimist.": (
        "The active Portal layer does not permit editing by this user."
    ),
    "Portali kihi redigeerimine on sisse lülitatud.": (
        "Portal layer editing is enabled."
    ),
    "Portali kihi redigeerimist ei saanud alustada.": (
        "Could not start editing the Portal layer."
    ),
    "Aktiivne Portali kiht pole redigeerimisrežiimis.": (
        "The active Portal layer is not in editing mode."
    ),
    "Muudatused salvestati Portalisse.": "Changes were saved to Portal.",
    "Muudatuste salvestamine Portalisse ebaõnnestus.": (
        "Could not save changes to Portal."
    ),
    "Kas loobuda aktiivse Portali kihi salvestamata muudatustest?": (
        "Discard unsaved changes to the active Portal layer?"
    ),
    "Portali kihi muudatused tühistati.": (
        "Portal layer changes were discarded."
    ),
    "Portali kihi muudatusi ei saanud tühistada.": (
        "Could not discard Portal layer changes."
    ),
    "Välitööde import": "Fieldwork import",
    "Geofüüsika välitööd": "Geophysical fieldwork",
    "CSV punktid ühendatakse failis olevas järjekorras üheks multipart-jooneks. Joon katkeb, kui järjestikuste punktide vahe on üle 50 m.": (
        "CSV points are connected in file order into one multipart line. "
        "The line is split wherever consecutive points are more than 50 m apart."
    ),
    "punkti": "points",
    "Aeg": "Date",
    "Seade": "Device",
    "Vastutaja": "Responsible person",
    "Märkus": "Notes",
    "CSV koordinaatsüsteem": "CSV coordinate reference system",
    "Vali…": "Select…",
    "Laadi Portalisse": "Upload to Portal",
    "Täida kohustuslikud väljad": "Complete the required fields",
    "Logi esmalt EGT Portalisse.": "Sign in to the EGS Portal first.",
    "Vali geofüüsika välitööde CSV": "Select geophysical fieldwork CSV",
    "CSV-faili lugemine ebaõnnestus": "Could not read the CSV file",
    "Geofüüsika välitööde valikuid laaditakse…": (
        "Loading geophysical fieldwork options…"
    ),
    "Geofüüsika välitööde sihtkiht ei ole joonkiht.": (
        "The geophysical fieldwork target is not a line layer."
    ),
    "Sisselogitud kasutajal puudub Geofüüsika välitööde kihile lisamise õigus.": (
        "The signed-in user cannot add features to the geophysical "
        "fieldwork layer."
    ),
    "Geofüüsika välitööde koodivalikuid ei saanud Portali kihist lugeda.": (
        "Could not read the geophysical fieldwork coded values from Portal."
    ),
    "Geofüüsika välitööde kihi lugemine ebaõnnestus": (
        "Could not read the geophysical fieldwork layer"
    ),
    "Salvesta või tühista esmalt Geofüüsika välitööde kihi pooleliolevad muudatused.": (
        "Save or discard the pending geophysical fieldwork edits first."
    ),
    "Koordinaatide teisendamine ebaõnnestus": (
        "Coordinate transformation failed"
    ),
    "CSV punktidest ei tekkinud ühtegi vähemalt kahe punktiga joont.": (
        "The CSV points did not form any line containing at least two points."
    ),
    "Multipart-joone loomine ebaõnnestus.": (
        "Could not create the multipart line."
    ),
    "Sihtkihi skeemist puuduvad väljad": "Fields missing from target schema",
    "Multipart-joont ei saanud Portali kihile lisada.": (
        "Could not add the multipart line to the Portal layer."
    ),
    "Geofüüsika välitööde üleslaadimine ebaõnnestus.": (
        "Could not upload the geophysical fieldwork."
    ),
    "Geofüüsika välitööd laaditi Portalisse": (
        "Geophysical fieldwork uploaded to Portal"
    ),
    "jooneosa": "line parts",
    "üksikpunkti jäeti välja": "isolated points omitted",
    "Kaardisildid": "Map labels",
    "Punktikihtide teksti suurus": "Point-layer text size",
    "EGT sildi sisu": "EGS label content",
    "VEKA ja SARV sildi sisu": "VEKA and SARV label content",
    "VEKA registrikood": "VEKA registry code",
    "SARV number": "SARV number",
    "Vali kuvatavad sildiread iga andmeallika jaoks eraldi. Puuduva väärtusega ridu ei kuvata.": (
        "Choose the label fields for each data source separately. "
        "Fields without values are omitted."
    ),
    "Puuraugud (PA)": "Boreholes (PA)",
    "Vaatluspunktid (VP)": "Observation points (VP)",
    "Nimi": "Name",
    "Alias": "Alias",
    "Pinnakatte paksus": "Quaternary cover thickness",
    "Aluspõhja reljeefi absoluutkõrgus": (
        "Bedrock-surface absolute elevation"
    ),
    "Indeks 0,5 m sügavusel (koos litoloogiaga)": (
        "Index at 0.5 m depth (with lithology)"
    ),
    "AP avamus (esimene aluspõhja indeks)": (
        "Bedrock outcrop (first bedrock index)"
    ),
    "Aluspõhja reljeef": "Bedrock surface",
    "0,5 m": "0.5 m",
    "AP avamus": "Bedrock outcrop",
    "Sildi sisu valikud rakenduvad EGT puuraukudele ja vaatluspunktidele. Teksti suurus rakendub ka SARV kohtadele ning VEKA puurkaevudele.": (
        "Label-content choices apply to EGS boreholes and observation "
        "points. Text size also applies to SARV locations and VEKA wells."
    ),
    "EGT kaardisiltide laadimine ebaõnnestus": (
        "Could not load EGS map-label data"
    ),
    "EGT filtrid": "EGS filters",
    "SARV filtrid": "SARV filters",
    "VEKA": "VEKA",
    "VEKA otsing ja filtrid": "VEKA search and filters",
    "VEKA puurkaevud": "VEKA wells",
    "VEKA puurkaev": "VEKA well",
    "VEKA puurkaevu valmis": "VEKA wells ready",
    "VEKA puurkaevu nähtaval": "VEKA wells visible",
    "VEKA puurkaeve laaditakse…": "Loading VEKA wells…",
    "VEKA seotud andmeid laaditakse…": "Loading related VEKA data…",
    "VEKA sümboloogia": "VEKA symbology",
    "VEKA kujundus rakendati.": "VEKA style applied.",
    "VEKA algkujundus taastati.": "Default VEKA style restored.",
    "Laadi VK kiht, et VEKA filtreid kasutada.": "Load the VK layer to use VEKA filters.",
    "Otsing": "Search",
    "Objekti andmed": "Object data",
    "Mine asukohta": "Go to location",
    "Liiguta kaart objekti asukohta, säilitades mõõtkava": (
        "Centre the map on the object while keeping the current scale"
    ),
    "Üldandmed": "Overview",
    "Läbilõige": "Log",
    "Läbilõiked": "Cross-sections",
    "Koondläbilõige": "Combined cross-section",
    "Läbilõike objektid": "Cross-section objects",
    "Koondläbilõige avaneb eraldi aknas, et Qeoloogi põhipaan jääks kompaktseks.": (
        "The combined cross-section opens in a separate window so the main "
        "Qeoloog panel stays compact."
    ),
    "Ava läbilõikeaken": "Open cross-section window",
    "Peida läbilõikeaken": "Hide cross-section window",
    "koondläbilõikel": "in the combined cross-section",
    "Lisa läbilõikele": "Add to cross-section",
    "Kaardijoone järgi": "Along map line",
    "Objektide järjekorra järgi": "By object order",
    "Võrdsete vahedega": "Equal spacing",
    "Joonista kaardil": "Draw on map",
    "Uus / tühjenda": "New / clear",
    "Kuva": "Show",
    "Absoluutkõrgus": "Absolute elevation",
    "Pikett": "Chainage",
    "Kõrvalekalle": "Offset",
    "GTK objekt": "GTK feature",
    "GTK kiht": "GTK layer",
    "Pööra": "Reverse",
    "Määra kõrgus": "Set elevation",
    "Puursüdamiku kastid": "Drill-core boxes",
    "Ühenda suudmed": "Connect wellheads",
    "Andmete absoluutkõrgus": "Recorded absolute elevation",
    "DEM maapinnaprofiil": "DEM ground profile",
    "DEM maapind": "DEM ground surface",
    "Mõõtkava": "Scale",
    "Horisontaalne px/m": "Horizontal px/m",
    "Vertikaalne px/m": "Vertical px/m",
    "Ctrl/Command + kerimine: vertikaalne suum. Shift + kerimine või horisontaalne kerimine: horisontaalne suum.": "Ctrl/Command + scroll: vertical zoom. Shift + scroll or horizontal scroll: horizontal zoom.",
    "DEM": "DEM",
    "Värskenda rasterkihte": "Refresh raster layers",
    "Loe DEM-profiil": "Sample DEM profile",
    "Kõrguskanal": "Elevation band",
    "Kaart ja eksport": "Map and export",
    "Kuva läbilõikejoon kaardil": "Show section line on map",
    "Lisa ülevaatekaart": "Include overview map",
    "Ekspordi SVG": "Export SVG",
    "Ekspordi PDF": "Export PDF",
    "Ekspordi": "Export",
    "Ekspordi ala": "Export area",
    "Joonista ala kaardil": "Draw area on map",
    "Vali polygon-fail": "Select polygon file",
    "Tühjenda ala": "Clear area",
    "Ekspordi ala pole valitud.": "No export area has been selected.",
    "Andmeallikad": "Data sources",
    "EGT (PA ja VP)": "EGS (boreholes and observation points)",
    "SARV (puursüdamikud)": "SARV (drill cores)",
    "VEKA (puurkaevud)": "VEKA (water wells)",
    "Leapfrog CSV": "Leapfrog CSV",
    "Väljundi CRS": "Output CRS",
    "Koordinaadid kirjutatakse valitud CRS-i; Leapfrogis tuleb määrata sama koordinaatsüsteem.": (
        "Coordinates are written in the selected CRS; configure the same "
        "coordinate system in Leapfrog."
    ),
    "Luuakse collar.csv, survey.csv ja interval.csv. Puuduva kalde ja asimuudiga puuraugud eksporditakse vertikaalselt alla (Dip 90°, Azimuth 0°).": (
        "Creates collar.csv, survey.csv and interval.csv. Holes without dip "
        "and azimuth data are exported vertically downward (Dip 90°, "
        "Azimuth 0°)."
    ),
    "VEKA lisaväljad": "Additional VEKA fields",
    "Veeanalüüside näitajad": "Water-analysis parameters",
    "Laadi näitajad": "Load parameters",
    "Filtreeri näitajaid": "Filter parameters",
    "Ekspordi Leapfrog CSV": "Export Leapfrog CSV",
    "Kohalikud andmeparandused": "Local data corrections",
    "Puursüdamiku kastide kohalikud parandused ei muuda EGT ega SARV andmebaasi.": (
        "Local drill-core box corrections do not modify the EGS or SARV "
        "database."
    ),
    "Salvestatud parandusi": "Saved corrections",
    "Ekspordi puursüdamiku parandused…": "Export drill-core corrections…",
    "Ekspordi puursüdamiku parandused": "Export drill-core corrections",
    "Valitud ala": "Selected area",
    "Polygon-faili ei õnnestunud avada.": (
        "The polygon file could not be opened."
    ),
    "Valitud fail ei ole polygonkiht.": (
        "The selected file is not a polygon layer."
    ),
    "Polygon-failis ei ole kasutatavat ala.": (
        "The polygon file does not contain a usable area."
    ),
    "Vali esmalt ekspordi ala.": "Select an export area first.",
    "Vali vähemalt üks andmeallikas.": "Select at least one data source.",
    "Vali ekspordi kaust": "Select export folder",
    "Ekspordifailid on juba olemas. Kas kirjutada üle?": (
        "Export files already exist. Overwrite them?"
    ),
    "Väljundi CRS ei ole kehtiv.": "The output CRS is not valid.",
    "Valitud alast ei leitud valitud allikate objekte. Kontrolli, et vastavad kihid on projekti laaditud.": (
        "No objects from the selected sources were found in the area. "
        "Check that the corresponding layers are loaded in the project."
    ),
    "kiht ei ole laaditud": "layer is not loaded",
    "Seotud andmeid laaditakse": "Loading related data",
    "Veeanalüüse laaditakse": "Loading water analyses",
    "Eksport ebaõnnestus": "Export failed",
    "hoiatust": "warnings",
    "Kaardile joonistatud ala": "Area drawn on map",
    "DEM puudub": "No DEM",
    "objekti": "objects",
    "objektil puudub absoluutkõrgus": "objects lack absolute elevation",
    "Kas eemaldada kõik koondläbilõike objektid?": (
        "Remove all combined cross-section objects?"
    ),
    "Koondläbilõikele pole objekte lisatud.": (
        "No objects have been added to the combined cross-section."
    ),
    "Eksporditud": "Exported",
    "Lisa läbilõikele vähemalt üks koordinaatide ja absoluutkõrgusega objekt.": (
        "Add at least one object with coordinates and absolute elevation."
    ),
    "Puursüdamik": "Drill core",
    "Muudetud": "Modified",
    "Redigeerimisrežiim": "Editing mode",
    "Muuda valitud kasti…": "Edit selected box…",
    "Taasta algandmed": "Restore source data",
    "Muudatused salvestuvad ainult selles arvutis.": (
        "Changes are saved only on this computer."
    ),
    "Vali kast ja vajuta „Muuda valitud kasti…“.": (
        "Select a box and click “Edit selected box…”."
    ),
    "Muuda puursüdamiku kasti": "Edit drill-core box",
    "Muudatus salvestatakse ainult sellesse arvutisse; EGT ega SARV algandmeid ei muudeta.": (
        "The change is saved only on this computer; the source data in EGS "
        "or SARV is not modified."
    ),
    "Kirje ID": "Record ID",
    "Kasti number": "Box number",
    "Ülemine sügavus, m": "Top depth, m",
    "Alumine sügavus, m": "Bottom depth, m",
    "Jäta tühjaks, kui puudub": "Leave blank if unavailable",
    "Vigane väärtus": "Invalid value",
    "Sügavus ja diameeter peavad olema arvud.": (
        "Depth and diameter must be numeric."
    ),
    "Sügavus ja diameeter ei saa olla negatiivsed.": (
        "Depth and diameter cannot be negative."
    ),
    "Alumine sügavus peab olema ülemisest sügavusest suurem.": (
        "Bottom depth must be greater than top depth."
    ),
    "Puursüdamiku staatuste valikuid laaditakse…": (
        "Loading drill-core status choices…"
    ),
    "Puursüdamiku staatuste laadimine ebaõnnestus": (
        "Could not load drill-core statuses"
    ),
    "Kastide sügavused kattuvad": "Core-box depths overlap",
    "Puursüdamiku kastide sügavusvahemikud kattuvad:": (
        "The drill-core box depth intervals overlap:"
    ),
    "Muuda ka kattuvat kasti…": "Edit the overlapping box too…",
    "Katkesta": "Cancel",
    "Kohalik redigeerimine": "Local editing",
    "Sellel kastil puudub püsiv kirje ID ja seda ei saa turvaliselt salvestada.": (
        "This box has no persistent record ID and cannot be saved safely."
    ),
    "Kas eemaldada selle kasti kohalikud parandused?": (
        "Remove the local corrections for this box?"
    ),
    "Proovid": "Samples",
    "Analüüsid": "Analyses",
    "Manused": "Attachments",
    "Eksemplarid": "Specimens",
    "Kirjandus": "Literature",
    "Allikas": "Source",
    "Seotud andmed": "Related data",
    "Puursüdamik olemas": "Drill core available",
    "Proovid olemas": "Samples available",
    "Analüüsid olemas": "Analyses available",
    "Manused olemas": "Attachments available",
    "Kõik": "All",
    "Jah": "Yes",
    "Ei": "No",
    "Autor": "Author",
    "Aasta": "Year",
    "Puurimise aasta": "Drilling year",
    "Puuraugu sügavus": "Borehole depth",
    "Otstarve": "Purpose",
    "Kasutus": "Use",
    "Põhjaveekogum": "Groundwater body",
    "Filtri paigutussügavus": "Filter placement depth",
    "Filtri algussügavus": "Filter top depth",
    "Filtri lõppsügavus": "Filter bottom depth",
    "Pumpamiskatse valik": "Pumping-test selection",
    "Mitme pumpamiskatse käsitlus": "Multiple pumping tests",
    "Deebit": "Discharge",
    "Eritootlikkus": "Specific capacity",
    "Veeproovi tulemused": "Water-sample results",
    "Laadi veeproovi näitajad": "Load water-quality parameters",
    "Veeproovi näitajaid laaditakse…": "Loading water-quality parameters…",
    "Veeproovi näitajad on valmis.": "Water-quality parameters are ready.",
    "Tulemuse valik": "Result selection",
    "Mitme veeproovi käsitlus": "Multiple water samples",
    "Tulemuse vahemik": "Result range",
    "Proovivõtu aasta": "Sampling year",
    "Alates": "From",
    "Kuni": "To",
    "Deebit on katsepumpamisel mõõdetud veehulk. Eritootlikkus = deebit / veetaseme alandus. Valik määrab, kuidas sama puurkaevu mitut pumpamiskatset käsitletakse.": (
        "Discharge is the flow measured during a pumping test. Specific "
        "capacity = discharge / drawdown. The selection determines how "
        "multiple tests from the same well are handled."
    ),
    "Sama näitaja teisendatavad ühikud ühendatakse ja tulemused kuvatakse valikus näidatud ühtsesse ühikusse.": (
        "Convertible units for the same parameter are combined and results "
        "are shown in the common unit displayed in the selector."
    ),
    "Vähemalt üks vaste": "At least one match",
    "Vähemalt üks tulemus sobib": "At least one result matches",
    "Uusim": "Latest",
    "Uusim tulemus": "Latest result",
    "Suurim": "Maximum",
    "Suurim tulemus": "Maximum result",
    "Väikseim": "Minimum",
    "Väikseim tulemus": "Minimum result",
    "Keskmine": "Mean",
    "Keskmine tulemus": "Mean result",
    "Lähtesta filtrid": "Reset filters",
    "Koondamine": "Aggregation",
    "Kujutusviis": "Rendering method",
    "Värv": "Colour",
    "Ikooni suurus": "Marker size",
    "Värv ja suurus": "Colour and size",
    "Klassifikatsioon": "Classification",
    "Kvantiilid": "Quantiles",
    "Võrdsed vahemikud": "Equal intervals",
    "Värviskaala": "Colour ramp",
    "Klasside arv": "Number of classes",
    "Ikooni suurus, mm": "Marker size, mm",
    "Kuva puuduvad andmed hallina": "Show missing values in grey",
    "Rakenda kujundus": "Apply style",
    "Taasta algkujundus": "Restore default style",
    "Valitud veeproovi näitaja": "Selected water-quality parameter",
    "Andmed puuduvad": "No data",
    "Nimi, aadress või ID": "Name, address or ID",
    "EGT, SARV ja VEKA": "EGS, SARV and VEKA",
    "Maavarade register": "Mineral Resources Register",
    "Geoloogiafond": "Geological Archive",
    "Maardlad": "Mineral deposits",
    "Aktiivsed mäeeraldised": "Active mining claims",
    "Aktiivsed uuringualad": "Active exploration areas",
    "Geoloogiafondi uuringualad": "Geological Archive survey areas",
    "Maardla": "Mineral deposit",
    "Aktiivne mäeeraldis": "Active mining claim",
    "Aktiivne uuringuala": "Active exploration area",
    "Geoloogiafondi uuringuala": "Geological Archive survey area",
    "Sisesta otsingusse nimi või registri ID.": (
        "Enter a name or registry ID in the search field."
    ),
    "Vali vähemalt üks objekti liik.": "Select at least one object type.",
    "kiht puudub seadetest": "layer is missing from the settings",
    "Mõni registripäring ebaõnnestus: ": (
        "One or more registry requests failed: "
    ),
    "Otsingut ei saanud käivitada.": "The search could not be started.",
    "Otsingutulemuse kiht puudub seadetest.": (
        "The search-result layer is missing from the settings."
    ),
    "Otsingutulemusel puudub püsiv registri ID.": (
        "The search result has no persistent registry ID."
    ),
    "Valitud registriobjekti kihi laadimine ebaõnnestus.": (
        "The selected registry-object layer could not be loaded."
    ),
    "Valitud registriobjekt lisati filtreeritud kihina.": (
        "The selected registry object was added as a filtered layer."
    ),
    "Testserver tagastas tundmatu REST-vastuse.": (
        "The test server returned an unknown REST response."
    ),
    "ArcGIS REST-viga": "ArcGIS REST error",
    "ArcGIS REST-vastus on korras, kuid QGIS ei avanud kihti": (
        "The ArcGIS REST response is valid, but QGIS could not open the layer"
    ),
    "Faktika REST-kontroll ebaõnnestus": (
        "The Faktika REST diagnostic request failed"
    ),
    "Faktika teenuse kihtide tuvastamine ebaõnnestus": (
        "Could not identify the Faktika service layers"
    ),
    "Portali kirjutamine on Qeoloogis välja lülitatud.": (
        "Portal writing is disabled in Qeoloog."
    ),
    "Portali kiht avati kirjutuskaitstult.": (
        "The Portal layer was opened read-only."
    ),
    "Portali kihi pooleliolevad muudatused tühistati, sest Qeoloog avab Portali andmeid ainult kirjutuskaitstult.": (
        "Pending Portal-layer edits were discarded because Qeoloog opens "
        "Portal data read-only."
    ),
    "Pealkiri": "Title",
    "Kivim": "Rock",
    "Sügavus": "Depth",
    "Registrikood": "Registry code",
    "Intervall": "Interval",
    "Koonda kattuvad": "Group overlaps",
    "Vigane alumine sügavus": "Invalid bottom depth",
    "Indeks": "Index",
    "Kihistik": "Formation",
    "Indeks / genees": "Index / genesis",
    "Vaatluspunktide 0,5 m siltide laadimine ebaõnnestus": (
        "Could not load observation-point labels at 0.5 m"
    ),
    "EGT detailandmete allikas": "EGT detail data source",
    "WFS – kiirem laadimine": "WFS – faster loading",
    "API – kiiremini uuenevad andmed": "API – faster data updates",
    "Puuraugud ja vaatluspunktid": "Boreholes and observation points",
    "API valik kasutab puuraukudel GEA API-t. Vaatluspunktide detailandmeid avalik GEA API praegu ei paku, seega kasutatakse nende puhul WFS-i.": (
        "The API option uses the GEA API for boreholes. The public GEA API "
        "does not currently expose observation-point details, so WFS is used "
        "for those."
    ),
    "Litoloogia": "Lithology",
    "Piiride sügavused": "Boundary depths",
    "Rakenda filtrid": "Apply filters",
    "Kastipiirid": "Core box boundaries",
    "Pinnakate": "Quaternary cover",
    "Aluspõhi": "Bedrock",
    "Aluskord": "Crystalline basement",
    "Muu / teadmata": "Other / unknown",
    "Puuraugud": "Boreholes",
    "Vaatluspunktid": "Observation points",
    "SARV - lokaliteedid": "SARV - localities",
    "SARV - uuringupunktid": "SARV - research sites",
    "SARV - puursüdamikud": "SARV - drill cores",
    "Lokaliteedid": "Localities",
    "Uuringupunktid": "Research sites",
    "Uuringupunkt": "Research site",
    "Puursüdamikud": "Drill cores",
    "Objekti liigid": "Object types",
    "Asukoht ja sügavus": "Location and depth",
    "Asukoht": "Location",
    "Asukohaviit": "Location reference",
    "korrastatud ID kattub": "curated ID matches",
    "Ainult kaardi praegune ulatus": "Current map extent only",
    "Min sügavus": "Minimum depth",
    "Max sügavus": "Maximum depth",
    "Eksemplarid olemas": "Specimens available",
    "Proovide filtrid": "Sample filters",
    "Analüüside filtrid": "Analysis filters",
    "Eksemplaride filtrid": "Specimen filters",
    "Eksemplari tüüp": "Specimen type",
    "Indeksi filtrid": "Index filters",
    "Sisaldab": "Contains",
    "Kuva valitud üksuste koondpaksus": "Show combined selected-unit thickness",
    "Puuraugu nime all kuvatakse kõigi valitud üksuste üks koondpaksus. Iga intervall arvestatakse üks kord; liitüksuste intervallide summa kuvatakse sulgudes. Puuraugu põhjani ulatuva üksuse paksuse järel kuvatakse +.": (
        "One combined thickness for all selected units is shown below the "
        "borehole name. Every interval is counted once; the sum of compound-"
        "unit intervals is shown in parentheses. A + is appended when a "
        "selected unit reaches the bottom of the borehole."
    ),
    "Proovi tüüp": "Sample type",
    "Proovi eesmärk": "Sample purpose",
    "Proovi staatus": "Sample status",
    "Analüüsi meetod": "Analysis method",
    "Analüüsi labor": "Analysis laboratory",
    "Tulemuse tüüp": "Result type",
    "Analüüsi näitaja": "Analysis parameter",
    "EGT ja SARV": "EGS and SARV",
    "Nimi, number või ID": "Name, number or ID",
    "Otsi": "Search",
    "Rakenda filtrina": "Apply as filter",
    "Otsingutulemused rakendati filtrina.": "Search results applied as a filter.",
    "Min": "Min",
    "Max": "Max",
    "Toiming": "Action",
    "Otsitakse…": "Searching…",
    "tulemust": "results",
    "Laadi otsimiseks esmalt kihid: ": "Load these layers before searching: ",
    "Kuvatakse esimesed 500.": "Showing the first 500.",
    "Puurauk": "Borehole",
    "Vaatluspunkt": "Observation point",
    "Lokaliteet": "Locality",
    "SARV seotud andmete filtrid päritakse vajadusel serverist. Tühi valik tähendab kõiki väärtusi.": "SARV related-data filters are queried from the server when needed. An empty selection means all values.",
    "EGT proovi- ja analüüsiindeksit laaditakse. Vajuta hetke pärast uuesti Otsi.": "The EGS sample and analysis index is loading. Press Search again in a moment.",
    "EGT seotud-andmete indeksit laaditakse. Vajuta hetke pärast uuesti Otsi.": "The EGS related-data index is loading. Press Search again in a moment.",
    "EGT kihid": "EGS layers",
    "Ulatus": "Extent",
    "Klõpsa objektil ja ava andmed": "Click an object to open its data",
    "Klõpsa kaardil puuraugul või vaatluspunktil.": "Click a borehole or observation point on the map.",
    "Väli": "Field",
    "Väärtus": "Value",
    "Kast": "Box",
    "Ülemine": "Top",
    "Alumine": "Bottom",
    "Diameeter": "Diameter",
    "Staatus": "Status",
    "Staatus / hoiukoht": "Status / storage",
    "Pildid": "Images",
    "Lisa kast…": "Add box…",
    "Lisa puursüdamiku kast": "Add drill-core box",
    "Tähis": "Identifier",
    "Tüüp": "Type",
    "Eesmärk": "Purpose",
    "Kood": "Code",
    "Kuupäev": "Date",
    "Meetod": "Method",
    "Labor": "Laboratory",
    "Näitajad": "Results",
    "Näitaja": "Parameter",
    "Tulemus": "Result",
    "Ühik": "Unit",
    "Liik": "Category",
    "Algus, m": "Top, m",
    "Lõpp, m": "Bottom, m",
    "Diameeter, mm": "Diameter, mm",
    "Ehitustooted": "Construction products",
    "Isolatsioon": "Isolation",
    "Kirjeldus": "Description",
    "Konstruktsioon": "Construction",
    "Pumpamiskatsed": "Pumping tests",
    "Veekeemia": "Water chemistry",
    "Veekeemia (andmed puuduvad)": "Water chemistry (no data)",
    "Protokoll": "Protocol",
    "Filter": "Screen",
    "Manteltoru / toru": "Casing / pipe",
    "Avatud / filtrita osa": "Open / unscreened section",
    "Puuri diameeter": "Bore diameter",
    "Manteltoru": "Casing",
    "Muu": "Other",
    "Laius ja Ø näitavad diameetrit millimeetrites": "Width and Ø show diameter in millimetres",
    "Veekompleks": "Aquifer system",
    "Sügavus, m": "Depth, m",
    "Staatiline veetase, m": "Static water level, m",
    "Staatiline veetase": "Static water level",
    "Dünaamiline veetase, m": "Dynamic water level, m",
    "Alandus, m": "Drawdown, m",
    "Deebit, l/s": "Discharge, l/s",
    "Eritootlikkus, l/(s·m)": "Specific capacity, l/(s·m)",
    "Kestus": "Duration",
    "Tehnoloogia": "Method / technology",
    "Analüüs": "Analysis",
    "Proovivõtu aeg": "Sampling date",
    "Ühtlustatud tulemus": "Normalized result",
    "Ühtlustatud ühik": "Normalized unit",
    "Proovi liik": "Sample type",
    "Fail": "File",
    "Link": "Link",
    "Teenus": "Service",
    "Nupu tähis": "Button code",
    "Kihi nimi": "Layer name",
    "Ingliskeelne nimi": "English name",
    "Teenuse URL": "Service URL",
    "Teenuse kiht": "Service layer",
    "WMS stiil": "WMS style",
    "Ikooni värv": "Icon colour",
    "Kihipuu asukoht": "Layer tree position",
    "Paiguta kihipuu alla": "Place at the bottom of the layer tree",
    "Kodu": "Home",
    "Paigutus": "Placement",
    "Põhiriba": "Toolbar",
    "Rippmenüü": "Drop-down menu",
    "Keelatud": "Disabled",
    "Üles": "Up",
    "Alla": "Down",
    "Eemalda": "Remove",
    "Vali...": "Choose...",
    "Loe kihid": "Read layers",
    "Uus": "New",
    "Lisa": "Add",
    "Uuenda": "Update",
    "Taasta algne kihikataloog": "Restore the default layer catalog",
    "Kasutajaliidese keel": "Interface language",
    "Eesti": "Estonian",
    "Inglise": "English",
    "Rippmenüüde nähtavus": "Drop-down visibility",
    "Sisse/välja režiim: korduv nupuvajutus eemaldab olemasoleva kihi projektist": "On/off mode: pressing a toolbar button again removes the existing layer",
    "Läbilõike andmed puuduvad": "No log data available",
    "Seotud andmeid laaditakse...": "Loading related data...",
    "seotud andmeid laaditakse…": "loading related data…",
    "Ava puursüdamiku kasti pilt": "Open drill core box image",
    "Pilt": "Image",
    "puuduv kast": "missing core box",
    "Viirutus: puursüdamiku kast puudub": "Hatching: no drill core box",
    "Vali ikooni värv": "Choose icon colour",
    "Laadi": "Load",
    "Seadista Qeoloogi": "Configure Qeoloog",
    "Lisa, muuda või eemalda WMS/WFS kihte": "Add, edit or remove WMS/WFS layers",
    "Lisa, muuda või eemalda WMS/WFS/SARV kihte": "Add, edit or remove WMS/WFS/SARV layers",
    "EGT objekti andmed": "EGS object data",
    "Klõpsa puuraugul või vaatluspunktil ja ava seotud andmed": "Click a borehole or observation point to open related data",
    "Klõpsa EGT või SARV punktil ja ava seotud andmed": "Click an EGS or SARV point to open related data",
    "Klõpsa EGT, SARV või VEKA punktil ja ava seotud andmed": "Click an EGS, SARV or VEKA point to open related data",
    "Lisa, muuda või eemalda WMS/WFS/SARV/VEKA kihte": "Add, edit or remove WMS/WFS/SARV/VEKA layers",
    "Kinnitatud EGT vaste": "Confirmed EGS match",
    "Võimalik EGT vaste": "Possible EGS match",
    "Kinnitatud SARV vaste": "Confirmed SARV match",
    "Võimalik SARV vaste": "Possible SARV match",
    "SARV vaste": "SARV match",
    "Vaste": "Match",
    "Ära lisa seost": "Do not add a link",
    "Kohalik seos": "Local link",
    "Kinnitatud seos valitakse ette. Uus kandidaat salvestub Qeoloogi kohaliku seosena alles koos objekti salvestamisega.": "A confirmed link is preselected. A new candidate is stored as a local Qeoloog link only when the object is saved.",
    "SARV vaste kandidaate kontrollitakse…": "Checking SARV match candidates…",
    "Ava": "Open",
    "Ava rakenduses": "Open in application",
    "Muuda SARV seost": "Edit SARV link",
    "Lisa SARV seos": "Add SARV link",
    "Taasta GEA seos": "Restore GEA link",
    "SARV seose haldus": "SARV link management",
    "Määra SARV seos": "Set SARV link",
    "SARV objekti tüüp": "SARV object type",
    "SARV objekti ID": "SARV object ID",
    "SARV objekt pole seotud": "No SARV object linked",
    "Kohalik parandus": "Local correction",
    "Vigane GEA sarv_id seos": "Invalid GEA sarv_id link",
    "Vigane Maa-ameti ID seos": "Invalid Land Board ID link",
    "Vigane lähte-ID": "Invalid source ID",
    "Vigase ID märge salvestati": "Invalid ID marker saved",
    "Ekspordi SARV seosed…": "Export SARV links…",
    "Ekspordi SARV seosed": "Export SARV links",
    "Eksport": "Export",
    "Lähtesta": "Reset",
    "Kinnita vaste": "Confirm match",
    "Eemalda vaste": "Remove match",
    "Käsitsi kinnitatud": "Manually confirmed",
    "ametlik ID kattub": "official ID matches",
    "SARV ID kattub": "SARV ID matches",
    "number kattub": "number matches",
    "nimi kattub": "name matches",
    "number matches": "number matches",
    "lokaliteet": "locality",
    "uuringupunkt": "research site",
    "puursüdamik": "drill core",
    "GEA SARV ID": "GEA SARV ID",
}


GROUP_LABELS = {
    "basemaps": "Aluskaardid",
    "geology": "Geoloogia",
    "studies": "Uuringud ja maavarad",
    "helpers": "Abikihid",
}


WELL_PASSPORT_LABEL = "Well passport number"


FIELD_LABELS_EN = {
    "gea_id": "GEA ID",
    "korrastatud_nr": "Corrected number",
    "ma_orig_id": "Original ID",
    "sarv_id": "SARV ID",
    "nimi": "Name",
    "alias": "Alias",
    "klassif_yksus_kood": "Unit class code",
    "yksus_kood": "Unit",
    "pikkus": "Length / depth",
    "vertikaalne_ulatus": "Vertical extent",
    "kande_alus": "Data source",
    "kande_alus_nr": "Source reference",
    "klassif_kande_alus": "Data source classification",
    "puursydamik": "Drill core",
    "klassif_puursydamik": "Drill core classification",
    "asukoha_tapsusklass": "Location accuracy",
    "klassif_asukoha_tapsusklass": "Location accuracy classification",
    "puurimisfirma": "Drilling company",
    "klassif_puurimisfirma": "Drilling company classification",
    "valmimise_kuupaev": "Completion date",
    "tellija": "Client",
    "klassif_tellija": "Client classification",
    "puurauk_staatus": "Borehole status",
    "klassif_puurauk_staatus": "Borehole status classification",
    "objekti_tyyp": "Object type",
    "klassif_objekti_tyyp": "Object type classification",
    "sygavuse_viis": "Depth method",
    "klassif_sygavuse_viis": "Depth method classification",
    "maaratud_veealune_sygavus": "Measured submerged depth",
    "markus": "Note",
    "xyz": "Coordinates",
    "esri_globalid": "Global ID",
    "lisamise_aeg": "Created",
    "muutmise_aeg": "Modified",
    "kaardistus_q": "Quaternary mapping",
    "kaardistus_ap": "Bedrock mapping",
    "eelis_id": "EELIS ID",
    "tyyp": "Type code",
    "otstarve": "Purpose",
    "staatus": "Status",
    "kkr_kood": "Registry code",
    "maayksus": "Cadastral unit",
    "maa_nimi": "Cadastral unit name",
    "katastri_nr": "Well cadastral number",
    "pass_nr": WELL_PASSPORT_LABEL,
    "seire_nr": "Monitoring number",
    "pvk_id": "Groundwater body ID",
    "pvk_nimi": "Groundwater body",
    "veekiht": "Aquifer index",
    "veekiht_nimi": "Aquifer",
    "aadress": "Address",
    "z_abs": "Ground elevation",
    "sygavus": "Depth",
    "kasutus": "Use",
    "puur_aasta": "Drilling year",
    "muut_aeg": "Modified",
    "puurija_nimi": "Driller",
    "puurija_kood": "Driller registry code",
    "puur_org": "Legacy drilling company code",
    "puur_viis_selg": "Drilling method",
    "puur_mark": "Drilling rig",
    "maardla_id": "Deposit ID",
    "registrikaardi_nr": "Registry card number",
    "egf_nr": "Geological archive reference",
    "maardla_nimetus": "Deposit name",
    "maardla_osa_nimetus": "Deposit part",
    "maavara": "Mineral resource",
    "pindala_ha": "Area (ha)",
    "vee_korvaldusmeetod": "Water removal method",
    "veepuhastuse_vajadus": "Need for water treatment",
    "veekaitse_meetmed": "Water-protection measures",
    "hydrogeol_taiendandmed": "Additional hydrogeological information",
    "maetehnilised_tingimused": "Mining conditions",
    "pohimaavara_kasutusala": "Primary-resource use",
    "kaasneva_maavara_kasutusala": "Associated-resource use",
    "geookoloogilised_tingimused": "Geoecological conditions",
    "aluspohjaline_maardla": "Bedrock deposit",
    "eksportimise_aeg": "Data export time",
    "maeeraldise_id": "Mining claim ID",
    "maeeraldise_kood": "Mining claim code",
    "maeeraldise_nimetus": "Mining claim name",
    "loa_nr": "Permit number",
    "loa_algus": "Permit start",
    "loa_lopp": "Permit end",
    "loa_valjastaja": "Permit issuer",
    "kaevandaja": "Operator",
    "eraldatud_varu": "Allocated reserve",
    "kasutuseesmark": "Intended use",
    "rekultiveerimissuund": "Restoration objective",
    "maeeraldise_olek": "Mining claim state",
    "loa_omanik": "Permit holder",
    "menetluses_klis": "Under KOTKAS processing",
    "meres": "At sea",
    "maaalune": "Underground",
    "pohimaavara": "Primary mineral resource",
    "kaasnev_maavara": "Associated mineral resource",
    "uuringuala_id": "Exploration-area ID",
    "uuringuala_kood": "Exploration-area code",
    "uuringuala_nimi": "Exploration-area name",
    "maardla_nimi": "Deposit name",
    "maavarad": "Mineral resources",
    "maavara_liigid": "Mineral-resource types",
    "kavandatav_kasutusala": "Planned use",
    "uuringu_teostaja": "Survey contractor",
    "litsentsi_nr": "Licence number",
    "litsentsi_valjastamise_kuupaev": "Licence issue date",
    "litsentsi_kehtivuse_kuupaev": "Licence expiry date",
    "loa_alguse_kuupaev": "Permit start",
    "loa_lopu_kuupaev": "Permit end",
    "uuringuala_olek": "Exploration-area state",
    "uuringuloa_valdaja": "Exploration permit holder",
    "loa_tyyp": "Permit type",
    "id": "ID",
    "egf_id": "Geological archive ID",
    "autor": "Author",
    "nimetus": "Title",
    "nimetus_orig": "Original title",
    "nimetus_eng": "English title",
    "aasta": "Year",
    "votmesona": "Keyword",
    "valdkond": "Field",
    "maardla": "Deposit",
    "maardla_reg_nr": "Deposit registry number",
    "piiratud_kuni": "Restricted until",
    "piiratud_pohjus": "Reason for restriction",
    "teostaja": "Survey contractor",
    "avalik_markus": "Public note",
    "uuringuala_suurus": "Survey-area size class",
    "muudetud": "Modified",
    "max_sygavus_m": "Maximum depth (m)",
    "ehitusgeo_uuringu_liik": "Engineering-geology survey type",
    "aruande_keel": "Report language",
    "pysilink": "Permanent report link",
    "eksporditud": "Data export date",
}

FIELD_LABELS_ET = {
    "z_abs": "Maapinna absoluutkõrgus",
    "puurija_nimi": "Puurija",
    "puurija_kood": "Puurija registrikood",
    "puur_org": "Puurinud ettevõtte kood (pärandandmed)",
    "puur_viis_selg": "Puurimisviis",
    "puur_mark": "Puurmasin",
    "maardla_id": "Maardla ID",
    "registrikaardi_nr": "Registrikaardi number",
    "egf_nr": "Geoloogiafondi viide",
    "maardla_nimetus": "Maardla nimetus",
    "maardla_osa_nimetus": "Maardla osa nimetus",
    "maavara": "Maavara",
    "pindala_ha": "Pindala (ha)",
    "vee_korvaldusmeetod": "Vee kõrvaldusmeetod",
    "veepuhastuse_vajadus": "Veepuhastuse vajadus",
    "veekaitse_meetmed": "Veekaitse meetmed",
    "hydrogeol_taiendandmed": "Hüdrogeoloogilised täiendandmed",
    "maetehnilised_tingimused": "Mäetehnilised tingimused",
    "pohimaavara_kasutusala": "Põhimaavara kasutusala",
    "kaasneva_maavara_kasutusala": "Kaasneva maavara kasutusala",
    "geookoloogilised_tingimused": "Geoökoloogilised tingimused",
    "aluspohjaline_maardla": "Aluspõhjaline maardla",
    "staatus": "Staatus",
    "muutmise_aeg": "Muutmise aeg",
    "eksportimise_aeg": "Andmete eksportimise aeg",
    "maeeraldise_id": "Mäeeraldise ID",
    "maeeraldise_kood": "Mäeeraldise kood",
    "maeeraldise_nimetus": "Mäeeraldise nimetus",
    "loa_nr": "Loa number",
    "loa_algus": "Loa algus",
    "loa_lopp": "Loa lõpp",
    "loa_valjastaja": "Loa väljastaja",
    "kaevandaja": "Kaevandaja",
    "eraldatud_varu": "Eraldatud varu",
    "kasutuseesmark": "Kasutuseesmärk",
    "rekultiveerimissuund": "Korrastamissuund",
    "maeeraldise_olek": "Mäeeraldise olek",
    "loa_omanik": "Loa omanik",
    "menetluses_klis": "KOTKAS-es menetluses",
    "meres": "Meres",
    "maaalune": "Maa-alune",
    "pohimaavara": "Põhimaavara",
    "kaasnev_maavara": "Kaasnev maavara",
    "uuringuala_id": "Uuringuala ID",
    "uuringuala_kood": "Uuringuala kood",
    "uuringuala_nimi": "Uuringuala nimi",
    "maardla_nimi": "Maardla nimi",
    "maavarad": "Maavarad",
    "maavara_liigid": "Maavara liigid",
    "kavandatav_kasutusala": "Kavandatav kasutusala",
    "uuringu_teostaja": "Uuringu teostaja",
    "litsentsi_nr": "Litsentsi number",
    "litsentsi_valjastamise_kuupaev": "Litsentsi väljastamise kuupäev",
    "litsentsi_kehtivuse_kuupaev": "Litsentsi kehtivuse kuupäev",
    "loa_alguse_kuupaev": "Loa alguse kuupäev",
    "loa_lopu_kuupaev": "Loa lõpu kuupäev",
    "uuringuala_olek": "Uuringuala olek",
    "uuringuloa_valdaja": "Uuringuloa valdaja",
    "loa_tyyp": "Loa tüüp",
    "id": "ID",
    "egf_id": "Geoloogiafondi ID",
    "autor": "Autor",
    "nimetus": "Nimetus",
    "nimetus_orig": "Algne nimetus",
    "nimetus_eng": "Ingliskeelne nimetus",
    "aasta": "Aasta",
    "votmesona": "Võtmesõna",
    "valdkond": "Valdkond",
    "maardla": "Maardla",
    "maardla_reg_nr": "Maardla registrinumber",
    "tellija": "Tellija",
    "piiratud_kuni": "Piiratud kuni",
    "piiratud_pohjus": "Piirangu põhjus",
    "teostaja": "Uuringu teostaja",
    "avalik_markus": "Avalik märkus",
    "uuringuala_suurus": "Uuringuala suurusklass",
    "muudetud": "Muudetud",
    "max_sygavus_m": "Maksimaalne sügavus (m)",
    "ehitusgeo_uuringu_liik": "Ehitusgeoloogilise uuringu liik",
    "aruande_keel": "Aruande keel",
    "pysilink": "Aruande püsilink",
    "eksporditud": "Andmete eksportimise kuupäev",
}


def translate(text, language):
    return EN.get(text, text) if language == "en" else text


def field_label(name, language):
    labels = FIELD_LABELS_EN if language == "en" else FIELD_LABELS_ET
    return labels.get(name, name)
