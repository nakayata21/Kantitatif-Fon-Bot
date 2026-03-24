
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
    "AAPL", "MSFT", "GOOG", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "PEP",
    "COST", "CSCO", "TMUS", "ADBE", "TXN", "QCOM", "AMGN", "INTU", "ISRG", "CMCSA",
    "AMD", "HON", "NFLX", "SBUX", "GILD", "BKNG", "AMAT", "ADI", "MDLZ", "VRTX",
    "REGN", "PANW", "MU", "MELI", "SNPS", "CDNS", "KLAC", "CSX", "PYPL", "MAR",
    "ASML", "ORLY", "MNST", "WBD", "LULU", "CRWD", "FTNT", "KDP", "CHTR", "CTAS",
    "DXCM", "ABNB", "WDAY", "ODFL", "ROST", "KHC", "PAYX", "IDXX", "BIIB", "AEP",
    "CPRT", "MRVL", "EA", "PCAR", "ILMN", "FAST", "VRSK", "CEG", "EXC", "DLTR",
    "VRSN", "ALGN", "WBA", "BKR", "BMRN", "SWKS", "CDW", "TSCO", "SIRI", "ZM",
    "CRSP", "DOCU", "PLTR", "RIVN", "LCID", "COIN", "U", "DKNG", "HOOD", "AFRM",
    "JD", "PDD", "BIDU", "NTES", "BABA", "TCEHY", "NIO", "XPEV", "LI",
    "SMCI", "ARM", "MSTR", "TGT", "WMT", "JPM", "BAC", "GS", "MS", "CVX", "XOM", "UNH",
    "LLY", "V", "MA", "ABBV", "KO", "PFE", "DIS", "NKE", "VZ", "T", "BA", "CAT",
    "IBM", "ORCL", "CRM", "INTC", "UBER", "ABNB", "SHOP", "SQ", "SE", "SNAP", "DASH"
]

DEFAULT_BIST_HISSELER = [
    "A1CAP", "ACSEL", "ADEL", "ADESE", "AEFES", "AFYON", "AGESA", "AGHOL", "AGROT", "AHGAZ", "AKBNK", "AKCNS",
    "AKENR", "AKFGY", "AKFYE", "AKGRT", "AKMGY", "AKSA", "AKSEN", "AKSGY", "AKSUE", "AKYHO", "ALARK", "ALBRK",
    "ALCAR", "ALCTL", "ALFAS", "ALGYO", "ALKA", "ALKIM", "ALMAD", "ALTNY", "ALVES", "ANELE", "ANGEN", "ANHYT",
    "ANSGR", "ARASE", "ARCLK", "ARDYZ", "ARENA", "ARSAN", "ARTMS", "ARZUM", "ASELS", "ASGYO", "ASTOR", "ASUZU",
    "ATAGY", "ATAKP", "ATATP", "ATEKS", "ATLAS", "ATSYH", "AVGYO", "AVHOL", "AVOD", "AVTUR", "AYCES", "AYDEM",
    "AYEN", "AYES", "AYGAZ", "AZTEK", "BAGFS", "BAKAB", "BALAT", "BANVT", "BARMA", "BASGZ", "BAYRK", "BEAYO",
    "BERA", "BEYAZ", "BFREN", "BGYO", "BIENY", "BIGCH", "BIMAS", "BINHO", "BIOEN", "BIZIM", "BJKAS", "BLCYT",
    "BMSCH", "BMSTL", "BNTAS", "BOBET", "BOSSA", "BOYNER", "BRIS", "BRKO", "BRKSN", "BRKVY", "BRLSM", "BRMEN",
    "BRSAN", "BRYAT", "BTCIM", "BUCIM", "BURCE", "BURVA", "BVSAN", "BYDNR", "CANTE", "CASA", "CATES", "CCOLA",
    "CELHA", "CEMAS", "CEMTS", "CEOEM", "CMENT", "CONSE", "CORBS", "COSMO", "CRDFA", "CRFSA", "CUSAN", "CVKMD",
    "CWENE", "DAGHL", "DAGI", "DAPGM", "DARDL", "DERHL", "DERIM", "DESA", "DESPC", "DEVA", "DGATE", "DGGYO",
    "DGNMO", "DIRIT", "DITAS", "DMRGD", "DMSAS", "DOAS", "DOBUR", "DOCO", "DOGUB", "DOHOL", "DOKTA", "DURDO",
    "DYOBY", "DZGYO", "EBEBK", "ECILC", "ECZYT", "EDATA", "EDIP", "EGEEN", "EGGUB", "EGPRO", "EGSER", "EKGYO",
    "EKIZ", "EKOS", "EKSUN", "ELITE", "EMKEL", "ENJSA", "ENKAI", "ENSRI", "ENTRA", "EPLAS", "ERBOS", "ERCB",
    "EREGL", "ERSU", "ESCAR", "ESCOM", "ESEN", "ETILR", "EUHOL", "EUKYO", "EUPWR", "EUREN", "EUYO", "EYGYO",
    "FADE", "FASIL", "FENER", "FLAP", "FMIZP", "FONET", "FORMT", "FORTE", "FRIGO", "FROTO", "FZLGY", "GARAN",
    "GARFA", "GEDIK", "GEDZA", "GENIL", "GENTS", "GEREL", "GESAN", "GIPTA", "GLBMD", "GLCVY", "GLRYH", "GLYHO",
    "GMTAS", "GOKNR", "GOLTS", "GOODY", "GOZDE", "GRNYO", "GRSEL", "GSDDE", "GSDHO", "GSRAY", "GUBRF", "GWIND",
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
    "NTHOL", "NUGYO", "NUHCM", "OBASE", "OBAMG", "ODAS", "OFSYM", "ONCSM", "ORCAY", "ORGE", "ORMA", "OSMEN",
    "OSTIM", "OTKAR", "OTTO", "OYAKC", "OYAYO", "OYLUM", "OYYAT", "OZGYO", "OZKGY", "OZRDN", "OZSUB", "PAGYO",
    "PAMEL", "PAPIL", "PARSN", "PASEU", "PATEK", "PCILT", "PEGYO", "PEKGY", "PENGD", "PENTA", "PETKM", "PETUN",
    "PGSUS", "PINSU", "PKART", "PKENT", "PLTUR", "PNLSN", "PNSUT", "POLHO", "POLTK", "PRDGS", "PRKAB", "PRKME",
    "PRZMA", "PSGYO", "PSUTC", "PTFS", "QNBFB", "QNBFL", "QUAGR", "RALYH", "RAYSG", "REEDR", "RNPOL", "RODRG",
    "ROYAL", "RTALB", "RUBNS", "RYGYO", "RYSAS", "SAHOL", "SAMAT", "SANEL", "SANFM", "SANKO", "SARKY", "SASA",
    "SAYAS", "SDTTR", "SEGYO", "SEKFK", "SEKUR", "SELEC", "SELGD", "SELVA", "SEYKM", "SILVR", "SINKO", "SNGYO",
    "SNICA", "SNKRN", "SNPAM", "SOKE", "SOKM", "SONME", "SRVGY", "SUMAS", "SUNTK", "SURGY", "SUWEN", "TABGD",
    "TARKM", "TATEN", "TATGD", "TAVHL", "TBORG", "TCELL", "TDGYO", "TEKTU", "TERA", "TETMT", "TEZOL", "TGSAS",
    "THYAO", "TKFEN", "TKNSA", "TLMAN", "TMPOL", "TMSN", "TOASO", "TRCAS", "TRGYO", "TRILC", "TSGYO", "TSKB",
    "TSPOR", "TTKOM", "TTRAK", "TUCLK", "TUKAS", "TUPRS", "TUREX", "TURGG", "TURSG", "UFUK", "ULAS", "ULKER",
    "ULUFA", "ULUSE", "ULUUN", "UMPAS", "UNLU", "USAK", "UZERB", "VAKBN", "VAKFN", "VAKKO", "VANGD", "VBTYZ",
    "VERTU", "VERUS", "VESBE", "VESTL", "VKFYO", "VKGYO", "VKING", "VRGYO", "YAPRK", "YATAS", "YAYLA", "YBTAS",
    "YEOTK", "YESIL", "YGGYO", "YGYO", "YIPLA", "YKBNK", "YKGYO", "YKSLN", "YONGA", "YUNSA", "YYAPI", "ZEDUR",
    "ZGOLD", "ZOREN", "ZRGYO"
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


