
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

TIMEFRAME_OPTIONS = {
    "4 Saatlik": {"base": "4h", "confirm": "1d", "bars": 500, "confirm_bars": 300},
    "Gunluk": {"base": "1d", "confirm": "1w", "bars": 300, "confirm_bars": 200},
    "Haftalik": {"base": "1w", "confirm": "1d", "bars": 220, "confirm_bars": 300},
    "Gunluk + Haftalik": {"base": "1d", "confirm": "1w", "bars": 300, "confirm_bars": 220, "multi": True},
}

DEFAULT_NASDAQ_HISSELER = [
    "AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA", "AVGO", "PEP", "COST",
    "CSCO", "AZN", "ADBE", "TXN", "QCOM", "TMUS", "AMGN", "INTU", "ISRG", "HON",
    "AMAT", "BKNG", "VRTX", "ADI", "MDLZ", "ADP", "PANW", "REGN", "MU", "SNPS",
    "CDNS", "MELI", "PYPL", "ASML", "KLAC", "CTAS", "CSX", "MAR", "MNST", "ORLY",
    "LULU", "WDAY", "MNST", "ADSK", "KDP", "CHTR", "CRWD", "DXCM", "AEP", "PAYX",
    "MSTR", "IDXX", "ROST", "EXC", "KHC", "BIIB", "PCAR", "EA", "MRVL", "CPRT",
    "ODFL", "AZO", "SGEN", "FAST", "VRSK", "SIRI", "ALGN", "CEG", "WBD", "EBAY",
    "ANSS", "TEAM", "DDOG", "JD", "BIDU", "DLTR", "LCID", "DOCU", "ZM", "OKTA"
]

DEFAULT_BIST_100 = [
    "AKBNK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "ALARK", "EKGYO", "ENKAI", "EREGL", "FROTO",
    "GARAN", "GUBRF", "HALKB", "HEKTS", "ISCTR", "KCHOL", "KOZAA", "KOZAL", "KRDMD", "ODAS",
    "OYAKC", "PGSUS", "SAHOL", "SASA", "SISE", "TCELL", "THYAO", "TOASO", "TUPRS", "YKBNK",
    "AEFES", "AGHOL", "AHGAZ", "AKCNS", "AKSA", "AKSEN", "ALBRK", "ALFAS", "ANSGR", "BAGFS",
    "BERA", "BRSAN", "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE", "DOAS", "DOHOL",
    "ECILC", "ECZYT", "EGEEN", "ENJSA", "EUPWR", "GESAN", "GLYHO", "GOZDE", "GWIND", "IPEKE",
    "ISDMR", "ISFIN", "ISGYO", "ISMEN", "IZMDC", "KARSN", "KAYSE", "KCAER", "KLRHO", "KMPUR",
    "KONTR", "KONYA", "KORDS", "MAVI", "MGROS", "MIATK", "MPARK", "OTKAR", "OYAYO", "OZKGY",
    "PENTA", "PETKM", "QUAGR", "REEDR", "SAYAS", "SDTTR", "SMRTG", "SOKM", "TABGD", "TARKM",
    "TATEN", "TAVHL", "TKFEN", "TKNSA", "TMSN", "TRGYO", "TSKB", "TTKOM", "TTRAK", "ULKER"
]

DEFAULT_BIST_HISSELER = [
    "A1CAP", "ACSEL", "ADEL", "ADESE", "AEFES", "AFYON", "AGESA", "AGHOL", "AGROT", "AHGAZ", "AKBNK", "AKCNS",
    "AKENR", "AKFGY", "AKFYE", "AKGRT", "AKMGY", "AKSA", "AKSEN", "AKSGY", "AKSUE", "AKYHO", "ALARK", "ALBRK",
    "ALCAR", "ALCTL", "ALFAS", "ALGYO", "ALKA", "ALKIM", "ALMAD", "ALTNY", "ALVES", "ANELE", "ANGEN", "ANHYT",
    "ANSGR", "ARASE", "ARCLK", "ARDYZ", "ARENA", "ARSAN", "ARTMS", "ARZUM", "ASELS", "ASGYO", "ASTOR", "ASUZU",
    "ATAGY", "ATAKP", "ATATP", "ATEKS", "ATLAS", "ATSYH", "AVGYO", "AVHOL", "AVOD", "AVPGY", "AVTUR", "AYCES", "AYDEM",
    "AYEN", "AYES", "AYGAZ", "AZTEK", "BAGFS", "BAKAB", "BALAT", "BANVT", "BARMA", "BASGZ", "BAYRK", "BEAYO",
    "BERA", "BEYAZ", "BFREN", "BGYO", "BIENY", "BIGCH", "BIMAS", "BINHO", "BIOEN", "BIZIM", "BJKAS", "BLCYT",
    "BMSCH", "BMSTL", "BNTAS", "BOBET", "BOSSA", "BOYNER", "BRIS", "BRKO", "BRKSN", "BRKVY", "BRLSM", "BRMEN",
    "BRSAN", "BRYAT", "BSOKE", "BTCIM", "BUCIM", "BURCE", "BURVA", "BVSAN", "BYDNR", "CANTE", "CASA", "CATES", "CCOLA",
    "CELHA", "CEMAS", "CEMTS", "CEOEM", "CIMSA", "CLEBI", "CMENT", "CONSE", "CORBS", "COSMO", "CRDFA", "CRFSA", "CUSAN", "CVKMD",
    "CWENE", "DAGHL", "DAGI", "DAPGM", "DARDL", "DERHL", "DERIM", "DESA", "DESPC", "DEVA", "DGATE", "DGGYO",
    "DGNMO", "DIRIT", "DITAS", "DMRGD", "DMSAS", "DOAS", "DOBUR", "DOCO", "DOGUB", "DOHOL", "DOKTA", "DSTKF", "DURDO",
    "DYOBY", "DZGYO", "EBEBK", "ECILC", "ECZYT", "EDATA", "EDIP", "EFORC", "EGEEN", "EGGUB", "EGPRO", "EGSER", "EKGYO",
    "EKIZ", "EKOS", "EKSUN", "ELITE", "EMKEL", "ENJSA", "ENKAI", "ENSRI", "ENTRA", "EPLAS", "ERBOS", "ERCB",
    "EREGL", "ERSU", "ESCAR", "ESCOM", "ESEN", "ETILR", "EUHOL", "EUKYO", "EUPWR", "EUREN", "EUYO", "EYGYO",
    "FADE", "FASIL", "FENER", "FLAP", "FMIZP", "FONET", "FORMT", "FORTE", "FRIGO", "FROTO", "FZLGY", "GARAN",
    "GARFA", "GEDIK", "GEDZA", "GENIL", "GENTS", "GEREL", "GESAN", "GIPTA", "GLBMD", "GLCVY", "GLRYH", "GLYHO",
    "GMTAS", "GOKNR", "GOLTS", "GOODY", "GOZDE", "GRNYO", "GRSEL", "GRTHO", "GSDDE", "GSDHO", "GSRAY", "GUBRF", "GWIND",
    "HALKB", "HATEK", "HATSN", "HDFGS", "HEDEF", "HEKTS", "HKTM", "HLGYO", "HTTBT", "HUBVC", "HUNER", "HURGZ",
    "ICBCT", "ICUGS", "IDGYO", "IEYHO", "IHAAS", "IHLAS", "IHLGM", "IHYAY", "IMASM", "INDES", "INFO", "INGRM",
    "INTEM", "INVEO", "INVES", "IPEKE", "ISATR", "ISBIR", "ISBTR", "ISCTR", "ISDMR", "ISFIN", "ISGSY", "ISGYO",
    "ISKPL", "ISKUR", "ISMEN", "ISSEN", "ISYAT", "ITTFH", "IZENR", "IZFAS", "IZINV", "IZMDC", "JANTS", "KAPLM",
    "KAREL", "KARSN", "KARTN", "KARYE", "KATMR", "KAYSE", "KCAER", "KCHOL", "KENT", "KERVN", "KERVT", "KFEIN",
    "KGYO", "KIMMR", "KLGYO", "KLKIM", "KLMSN", "KLNMA", "KLRHO", "KLSYN", "KMPUR", "KNFRT", "KOCMT", "KONKA",
    "KONTR", "KONYA", "KOPOL", "KORDS", "KOZAA", "KOZAL", "KRDMA", "KRDMB", "KRDMD", "KRGYO", "KRONT", "KRPLS",
    "KRSTL", "KRTEK", "KRVGD", "KTSKR", "KSTUR", "KTLEV", "KUTPO", "KUYAS", "KZBGY", "KZGYO", "LIDER",
    "LINK", "LKMNH", "LMKDC", "LOGO", "LRSHO", "LUKSK", "MAALT", "MACKO", "MACRO", "MAGEN", "MAKIM", "MAKTK",
    "MANAS", "MARKA", "MARTI", "MAVI", "MAXDD", "MEDTR", "MEGAP", "MEKAG", "MEPET", "MERCN", "MERIT", "MERKO",
    "METRO", "METUR", "MGROS", "MHRGY", "MIATK", "MIPAZ", "MMCAS", "MNDRS", "MNDTR", "MOBTL", "MOGAN", "MPARK",
    "MRGYO", "MRSHL", "MSGYO", "MTRKS", "MTRYO", "MUHAL", "MUREN", "MZHLD", "NATEN", "NETAS", "NIBAS", "NTGAZ",
    "NTHOL", "NUGYO", "NUHCM", "OBASE", "OBAMS", "ODAS", "OFSYM", "ONCSM", "ORCAY", "ORGE", "ORMA", "OSMEN",
    "OSTIM", "OTKAR", "OTTO", "OYAKC", "OYAYO", "OYLUM", "OYYAT", "OZGYO", "OZKGY", "OZRDN", "OZSUB", "PAGYO",
    "PAHOL", "PAMEL", "PAPIL", "PARSN", "PASEU", "PATEK", "PCILT", "PEGYO", "PEKGY", "PENGD", "PENTA", "PETKM", "PETUN",
    "PGSUS", "PINSU", "PKART", "PKENT", "PLTUR", "PNLSN", "PNSUT", "POLHO", "POLTK", "PRDGS", "PRKAB", "PRKME",
    "PRZMA", "PSGYO", "PSUTC", "PTFS", "QNBFB", "QNBFL", "QUAGR", "RALYH", "RAYSG", "REEDR", "RNPOL", "RODRG",
    "ROYAL", "RTALB", "RUBNS", "RYGYO", "RYSAS", "SAHOL", "SAMAT", "SANEL", "SANFM", "SANKO", "SARKY", "SASA",
    "SAYAS", "SDTTR", "SEGYO", "SEKFK", "SEKUR", "SELEC", "SELGD", "SELVA", "SEYKM", "SILVR", "SINKO", "SISE", "SKBNK", "SMRTG", "SNGYO",
    "SNICA", "SNKRN", "SNPAM", "SOKE", "SOKM", "SONME", "SRVGY", "SUMAS", "SUNTK", "SURGY", "SUWEN", "TABGD",
    "TARKM", "TATEN", "TATGD", "TAVHL", "TBORG", "TCELL", "TDGYO", "TEKTU", "TERA", "TETMT", "TEZOL", "TGSAS",
    "THYAO", "TKFEN", "TKNSA", "TLMAN", "TMPOL", "TMSN", "TOASO", "TRCAS", "TRGYO", "TRILC", "TSGYO", "TSKB",
    "TSPOR", "TTKOM", "TTRAK", "TUCLK", "TUKAS", "TUPRS", "TUREX", "TURGG", "TURSG", "UFUK", "ULAS", "ULKER",
    "ULUFA", "ULUSE", "ULUUN", "UMPAS", "UNLU", "USAK", "UZERB", "VAKBN", "VAKFN", "VAKKO", "VANGD", "VBTYZ",
    "VERTU", "VERUS", "VESBE", "VESTL", "VKFYO", "VKGYO", "VKING", "VRGYO", "YAPRK", "YATAS", "YAYLA", "YBTAS",
    "YEOTK", "YESIL", "YGGYO", "YGYO", "YIPLA", "YKBNK", "YKGYO", "YKSLN", "YONGA", "YUNSA", "YYAPI", "ZEDUR",
    "ZGOLD", "ZOREN", "ZRGYO"
]

DEFAULT_BIST_30 = [
    "AKBNK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "ALARK", "EKGYO", "ENKAI", "EREGL", "FROTO",
    "GARAN", "GUBRF", "HALKB", "HEKTS", "ISCTR", "KCHOL", "KOZAA", "KOZAL", "KRDMD", "ODAS",
    "OYAKC", "PGSUS", "SAHOL", "SASA", "SISE", "TCELL", "THYAO", "TOASO", "TUPRS", "YKBNK"
]

DEFAULT_CRYPTO_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "USDCUSDT", "ADAUSDT",
    "DOGEUSDT", "TRXUSDT", "AVAXUSDT", "DOTUSDT", "SHIBUSDT", "LINKUSDT", "TONUSDT",
    "XLMUSDT", "SUIUSDT", "BCHUSDT", "LTCUSDT", "PEPEUSDT", "NEARUSDT", "HBARUSDT",
    "UNIUSDT", "APTUSDT", "LEOUSDT", "ICPUSDT", "RENDERUSDT", "ETCUSDT", "ARBUSDT",
    "CROUSDT", "KASUSDT", "FETUSDT", "VETUSDT", "FILUSDT", "STXUSDT", "OMUSDT",
    "TAOUSDT", "MNTUSDT", "OPUSDT", "WIFUSDT", "RUNEUSDT", "ALGOUSDT", "ATOMUSDT",
    "BONKUSDT", "AAVEUSDT", "THETAUSDT", "IMXUSDT", "ENAUSDT", "ARUSDT", "SEIUSDT",
    "FLOKIUSDT", "FLOWUSDT", "JUPUSDT", "BEAMUSDT", "LDOUSDT", "PYTHUSDT", "EGLDUSDT",
    "JASMYUSDT", "GALAUSDT", "COREUSDT", "TIAUSDT", "STRKUSDT", "DYDXUSDT", "BRETTUSDT",
    "MKRUSDT", "PENDLEUSDT", "BGBUSDT", "GRTUSDT", "AKTUSDT", "FTMUSDT", "RAYUSDT",
    "NOTUSDT", "POPCATUSDT", "MOGUSDT", "ONDOUSDT", "ENSUSDT", "QNTUSDT", "MASKUSDT",
    "AXSUSDT", "MANAUSDT", "SANDUSDT", "ROSEUSDT", "KAVAUSDT", "CRVUSDT", "GNOUSDT",
    "NEOUSDT", "CFXUSDT", "JTOUSDT", "CHZUSDT", "AEVOUSDT", "DYMUSDT", "MINAUSDT",
    "BLURUSDT", "WLDUSDT", "KCSUSDT", "XDCUSDT", "ZKUSDT", "IOUSDT", "ZILUSDT", "BOMEUSDT"
]

# Dip skoru — scoring.py ve Streamlit listeleri aynı eşikleri kullanır
DIP_SOLID_BOTTOM_MIN = 45  # "sağlam dip": DİPTEN DÖNÜYOR, odak üst bandı
DIP_SOFT_LIST_MIN = 35  # "dip adayı" listesi; odak skorunda (dip-35) ölçeği
DIP_ODAK_WEAK_MIN = 30  # Odak skorunda zayıf dip katkısı eşiği
DIP_BB_OVERBOUGHT_RATIO = 0.85  # BB % üstü: dip puanına ceza

BIST_SECTORS = {
    "AKBNK": "Banka", "GARAN": "Banka", "ISCTR": "Banka", "YKBNK": "Banka", "HALKB": "Banka", "VAKBN": "Banka",
    "THYAO": "Ulaştırma", "PGSUS": "Ulaştırma", "TAVHL": "Ulaştırma",
    "EREGL": "Demir Çelik", "KRDMD": "Demir Çelik", "ISDMR": "Demir Çelik",
    "TUPRS": "Enerji/Petrol", "PETKM": "Kimya", "SASA": "Kimya", "HEKTS": "Kimya/Tarım",
    "ASELS": "Savunma", "TCELL": "İletişim", "TTKOM": "İletişim", "SISE": "Cam",
    "KCHOL": "Holding", "SAHOL": "Holding", "AGHOL": "Holding", "DOHOL": "Holding",
    "BIMAS": "Perakende", "MGROS": "Perakende", "SOKM": "Perakende",
    "ASTOR": "Enerji", "EUPWR": "Enerji", "SMRTG": "Enerji", "KONTR": "Enerji", "GESAN": "Enerji",
    "DOAS": "Otomotiv", "FROTO": "Otomotiv", "TOASO": "Otomotiv", "TTRAK": "Otomotiv",
    "ENJSA": "Enerji", "AKSEN": "Enerji", "CWENE": "Enerji", "ALARK": "Holding",
}


