import json

# Full strain data list
STRAINS = [
    {
        "name": "Apple Fritter",
        "lineage": "Sour Apple x Animal Cookies",
        "breeder": "Lump's Flowers",
        "breeder_url": "https://www.lumpysflowers.com",
        "image_url": "https://iili.io/3qJnedN.jpg",
        "notes": "Breeder cut. Clone-only strain from Lumpy's Flowers (original Apple Fritter)."
    },
    {
        "name": "Apple Tartz",
        "lineage": "Runtz x Apple Fritter",
        "breeder": "Clearwater Genetics",
        "breeder_url": "https://www.instagram.com/clearwatergenetics",
        "image_url": "https://i.imgur.com/oI9nOs9.png",
        "notes": "Clones Direct Cut. Noted for candy-like sweet aroma."
    },
    {
        "name": "Sherb Cake",
        "lineage": "Sunset Sherbert x Wedding Cake",
        "breeder": "Seed Junky Genetics",
        "breeder_url": "https://www.seedjunkygenetics.com",
        "image_url": "https://iili.io/3qJ78Fe.jpg",
        "notes": "Gassy, creamy aroma with berry undertones."
    },
    {
        "name": "Blumosa",
        "lineage": "Blue Cookies x Mimosa",
        "breeder": "Mosca",
        "breeder_url": "https://www.moscaseeds.com",
        "image_url": "https://iili.io/3qJuWXt.jpg",
        "notes": "Mosca Seeds hybrid with citrus blue Powerade-like aroma."
    },
    {
        "name": "Blue Dream",
        "lineage": "Blueberry x Haze",
        "breeder": "Unknown",
        "image_url": "https://iili.io/3q3U4BR.png",
        "notes": "Santa Cruz cut."
    },
    {
        "name": "Bubba Kush",
        "lineage": "OG Kush x Unknown (Pre-98)",
        "breeder": "Unknown",
        "image_url": "https://iili.io/3q3gm91.jpg",
        "notes": "Pre-98 cut."
    },
    {
        "name": "Bubblegum Cookies",
        "lineage": "Bubblegum x Girl Scout Cookies",
        "breeder": "Archive",
        "breeder_url": "https://www.instagram.com/archiveseedbank",
        "image_url": "https://iili.io/3q36M8B.png",
        "notes": "Clones Direct cut."
    },
    {
        "name": "Candy Rain",
        "lineage": "Gelato x London Pound Cake",
        "breeder": "Cookies Fam",
        "breeder_url": "https://cookies.co",
        "image_url": "https://iili.io/3fSlD92.png",
        "notes": "Indica-leaning hybrid by Cookies. Sweet dessert and skunky aroma."
    },
    {
        "name": "Cinderella's Dream",
        "lineage": "Cinex x Blue Dream",
        "breeder": "Reign City",
        "breeder_url": "https://www.instagram.com/reigncity_",
        "image_url": "https://iili.io/3q3PZWg.jpg",
        "notes": "Breeder cut"
    },
    {
        "name": "Enchanted Platinum",
        "lineage": "Cinderella's Dream x White Gold F2",
        "breeder": "Reign City",
        "breeder_url": "https://www.instagram.com/reigncity_",
        "image_url": "https://iili.io/3qwrCZP.jpg",
        "notes": "Breeder cut"
    },
    {
        "name": "Gelato Cake",
        "lineage": "Gelato x Wedding Cake",
        "breeder": "Unknown",
        "image_url": "https://iili.io/3q3igQn.jpg",
        "notes": ""
    },
    {
        "name": "Georgia Pie",
        "lineage": "Gelatti x Kush Mints",
        "breeder": "Seed Junky Genetics",
        "breeder_url": "https://www.seedjunkygenetics.com",
        "image_url": "https://i.imgur.com/Rc9ossa.png",
        "notes": "Sourced from Archive Portland."
    },
    {
        "name": "GG4",
        "lineage": "Chem's Sister x Sour Dubb x Chocolate Diesel",
        "breeder": "GG Strains",
        "breeder_url": "https://www.ggstrains.com",
        "image_url": "https://i.imgur.com/VGcnIPT.png",
        "notes": "Josey's cut (Original Glue aka Gorilla Glue #4)."
    },
    {
        "name": "GMO",
        "lineage": "Chemdog D x Girl Scout Cookies (Forum)",
        "breeder": "Mamiko",
        "breeder_url": "https://www.instagram.com/mamikoseeds",
        "image_url": "https://i.imgur.com/TtUSFQh.png",
        "notes": "SkunkMasterFlex cut (aka Garlic Cookies)."
    },
    {
        "name": "Lottery 2.0",
        "lineage": "Lottery x White Gold (Biscotti x Dosidos) F2",
        "breeder": "Reign City",
        "breeder_url": "https://www.instagram.com/reigncity_",
        "image_url": "https://i.imgur.com/hN9uz7I.png",
        "notes": "Breeder cut"
    },
    {
        "name": "Orange Push Pop",
        "lineage": "Triangle Kush x Orange Cookies",
        "breeder": "Seed Junky Genetics",
        "breeder_url": "https://www.seedjunkygenetics.com",
        "image_url": "https://iili.io/3qFq1I9.jpg",
        "notes": "Reign City cut."
    },
    {
        "name": "Pineapple Haze",
        "lineage": "Pineapple x Haze",
        "breeder": "Barney's Farm",
        "breeder_url": "https://www.barneysfarm.com",
        "image_url": "https://i.imgur.com/soQWRBo.jpeg",
        "notes": "Clones Direct cut"
    },
    {
        "name": "Platinum Garlic",
        "lineage": "GMO Cookies x Platinum Cookies",
        "breeder": "InHouse",
        "breeder_url": "https://www.instagram.com/inhouse_genetics_official",
        "image_url": "https://i.imgur.com/OBuiFf8.png",
        "notes": "Turns blue and smells super strong!"
    },
    {
        "name": "Rainbow Sherbet #11",
        "lineage": "Pink Guava x Sunset Sherbert",
        "breeder": "Deo Farms",
        "breeder_url": "https://www.instagram.com/deo_farms",
        "image_url": "https://i.imgur.com/cCTOdIW.png",
        "notes": "Phenotype #11 selected by Wizard Trees/Deo."
    },
    {
        "name": "Redline Haze",
        "lineage": "Unknown",
        "breeder": "Piff Coast Farms",
        "breeder_url": "https://www.instagram.com/piffcoast",
        "image_url": "https://i.imgur.com/VMbCBOC.png",
        "notes": "Breeder cut. East Coast 'Piff' Haze lineage (clone-only, exact genetics unknown)."
    },
    {
        "name": "Sour Tropicookies",
        "lineage": "Tropicanna Cookies x (Sour Diesel x Animal Cookies Bx1)",
        "breeder": "Reign City",
        "breeder_url": "https://www.instagram.com/reigncity_",
        "image_url": "https://i.imgur.com/hN9uz7I.png",
        "notes": "Breeder cut"
    },
    {
        "name": "Triangle Kush",
        "lineage": "Unknown",
        "breeder": "Unknown",
        "image_url": "https://i.imgur.com/dDSNSiB.png",
        "notes": "Original Florida cut. Not an S1 or hybrid."
    },
    {
        "name": "Trinity",
        "lineage": "Unknown",
        "breeder": "Unknown",
        "image_url": "https://i.imgur.com/hN9uz7I.png",
        "notes": "1980s clone-only from Pacific NW (3-way NorCal hybrid, exact lineage lost)."
    },
    {
        "name": "Trop Cherries",
        "lineage": "Tropicana Cookies x Cherry Cookies",
        "breeder": "Relentless Genetics",
        "breeder_url": "https://www.instagram.com/relentless__genetics",
        "image_url": "https://i.imgur.com/eh63Bpj.png",
        "notes": "Breeder cut"
    },
    {
        "name": "White Truffle",
        "lineage": "Peanut Butter Breath x GG4",
        "breeder": "Fresh Coast Seed Company",
        "breeder_url": "https://freshcoastseed.co",
        "image_url": "https://i.imgur.com/qJkn5rt.png",
        "notes": "Elite phenotype of Fresh Coast's Gorilla Butter (selected by BeLeaf, clone-only)."
    },
    {
        "name": "Zookies",
        "lineage": "Animal Cookies x Gorilla Glue #4",
        "breeder": "Alien Labs",
        "breeder_url": "https://alienlabs.org",
        "image_url": "https://i.imgur.com/PpNIRvJ.png",
        "notes": "Breeder cut"
    }
]

STRAIN_NAMES = sorted([strain["name"] for strain in STRAINS])

def get_strain_by_name(name):
    return next((strain for strain in STRAINS if strain["name"] == name), None)
