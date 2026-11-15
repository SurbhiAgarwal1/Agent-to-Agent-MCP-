"""Synthetic directory of hospitals in Bengaluru.

Names are real, widely known hospitals, but the coordinates are APPROXIMATE (placed by locality, not surveyed) and the
list is not exhaustive. It exists so hospital staff can name their hospital in plain words and every request is stored
against a hospital. A hospital that is not listed is registered the first time someone requests blood for it.

Each row: (name, short names people actually type, area, latitude, longitude)
"""

BANGALORE_CENTRE = (12.9716, 77.5946)

HOSPITALS = [
    ("Narayana Hrudayalaya (Narayana Health City), Bommasandra", ("narayana hrudayalaya", "narayana health city", "narayana health", "narayana institute of cardiac sciences"), "Bommasandra", 12.8056, 77.6937),
    ("Narayana Multispeciality Hospital, HSR Layout", ("narayana hsr", "narayana multispeciality"), "HSR Layout", 12.9140, 77.6410),
    ("Manipal Hospital, Old Airport Road", ("manipal old airport road", "manipal hospital old airport"), "Old Airport Road", 12.9585, 77.6483),
    ("Manipal Hospital, Whitefield", ("manipal whitefield",), "Whitefield", 12.9889, 77.7515),
    ("Manipal Hospital, Sarjapur Road", ("manipal sarjapur",), "Sarjapur Road", 12.9122, 77.6840),
    ("Manipal North Side Hospital, Yeshwanthpur", ("manipal north side", "manipal yeshwanthpur"), "Yeshwanthpur", 13.0165, 77.5470),
    ("Fortis Hospital, Bannerghatta Road", ("fortis bannerghatta",), "Bannerghatta Road", 12.8945, 77.6010),
    ("Fortis Hospital, Cunningham Road", ("fortis cunningham",), "Cunningham Road", 12.9881, 77.5913),
    ("Fortis Hospital, Rajajinagar", ("fortis rajajinagar",), "Rajajinagar", 12.9996, 77.5521),
    ("Fortis Hospital, Nagarbhavi", ("fortis nagarbhavi",), "Nagarbhavi", 12.9627, 77.5010),
    ("Apollo Hospital, Bannerghatta Road", ("apollo bannerghatta", "apollo bgs"), "Bannerghatta Road", 12.8957, 77.5979),
    ("Apollo Hospital, Jayanagar", ("apollo jayanagar",), "Jayanagar", 12.9279, 77.5826),
    ("Apollo Spectra Hospital, Koramangala", ("apollo spectra", "apollo koramangala"), "Koramangala", 12.9352, 77.6245),
    ("Aster CMI Hospital, Hebbal", ("aster cmi", "aster hebbal"), "Hebbal", 13.0520, 77.5936),
    ("Aster RV Hospital, JP Nagar", ("aster rv", "aster jp nagar"), "JP Nagar", 12.8985, 77.5844),
    ("Sakra World Hospital, Marathahalli", ("sakra world", "sakra"), "Marathahalli", 12.9330, 77.6970),
    ("Columbia Asia Hospital, Hebbal", ("columbia asia hebbal",), "Hebbal", 13.0480, 77.5970),
    ("Columbia Asia Hospital, Yeshwanthpur", ("columbia asia yeshwanthpur",), "Yeshwanthpur", 13.0245, 77.5470),
    ("Columbia Asia Hospital, Whitefield", ("columbia asia whitefield",), "Whitefield", 12.9950, 77.7480),
    ("Cloudnine Hospital, Jayanagar", ("cloudnine jayanagar",), "Jayanagar", 12.9258, 77.5860),
    ("Cloudnine Hospital, Old Airport Road", ("cloudnine old airport",), "Old Airport Road", 12.9600, 77.6460),
    ("Sparsh Hospital, Infantry Road", ("sparsh infantry", "sparsh hospital"), "Infantry Road", 12.9850, 77.6000),
    ("Sparsh Hospital, Yeshwanthpur", ("sparsh yeshwanthpur",), "Yeshwanthpur", 13.0250, 77.5440),
    ("St. John's Medical College Hospital, Koramangala", ("st john's", "st johns", "saint john's", "st john"), "Koramangala", 12.9296, 77.6179),
    ("Victoria Hospital, K.R. Market", ("victoria hospital", "bangalore medical college", "bmcri"), "K.R. Market", 12.9644, 77.5737),
    ("Bowring and Lady Curzon Hospital, Shivajinagar", ("bowring", "lady curzon"), "Shivajinagar", 12.9840, 77.6030),
    ("Kidwai Memorial Institute of Oncology", ("kidwai", "kmio"), "Dairy Circle", 12.9397, 77.5967),
    ("NIMHANS", ("nimhans", "national institute of mental health"), "Hosur Road", 12.9423, 77.5952),
    ("Sri Jayadeva Institute of Cardiovascular Sciences and Research", ("jayadeva",), "Jayanagar 9th Block", 12.9177, 77.5990),
    ("Vani Vilas Hospital", ("vani vilas",), "K.R. Market", 12.9573, 77.5726),
    ("Indira Gandhi Institute of Child Health", ("indira gandhi institute of child health", "igich"), "Dairy Circle", 12.9392, 77.5958),
    ("Rajiv Gandhi Institute of Chest Diseases", ("rajiv gandhi institute of chest diseases", "rgicd", "chest diseases"), "Bannerghatta Road", 12.8870, 77.5975),
    ("Minto Ophthalmic Hospital", ("minto",), "Chamrajpet", 12.9606, 77.5738),
    ("M S Ramaiah Memorial Hospital, MSR Nagar", ("ramaiah", "msr hospital", "m s ramaiah"), "MSR Nagar", 13.0305, 77.5648),
    ("BGS Gleneagles Global Hospital, Kengeri", ("gleneagles", "bgs global", "bgs gleneagles"), "Kengeri", 12.9015, 77.4868),
    ("Mallya Hospital, Vittal Mallya Road", ("mallya",), "Vittal Mallya Road", 12.9697, 77.5951),
    ("Vikram Hospital, Millers Road", ("vikram hospital",), "Millers Road", 12.9953, 77.5953),
    ("Baptist Hospital, Hebbal", ("baptist",), "Hebbal", 13.0434, 77.5933),
    ("Sagar Hospitals, Kumaraswamy Layout", ("sagar hospital", "sagar hospitals"), "Kumaraswamy Layout", 12.8978, 77.5601),
    ("HOSMAT Hospital, Ashok Nagar", ("hosmat",), "Ashok Nagar", 12.9726, 77.6068),
    ("HCG Cancer Hospital, K.R. Road", ("hcg",), "K.R. Road", 12.9566, 77.5753),
    ("Motherhood Hospital, Indiranagar", ("motherhood",), "Indiranagar", 12.9747, 77.6409),
    ("Rainbow Children's Hospital, Marathahalli", ("rainbow children", "rainbow hospital"), "Marathahalli", 12.9591, 77.6974),
    ("Chinmaya Mission Hospital, Indiranagar", ("chinmaya mission",), "Indiranagar", 12.9783, 77.6401),
    ("C.V. Raman General Hospital, Indiranagar", ("cv raman", "c v raman", "c.v. raman"), "Indiranagar", 12.9810, 77.6480),
    ("Jayanagar General Hospital", ("jayanagar general",), "Jayanagar", 12.9292, 77.5831),
    ("K.C. General Hospital, Malleswaram", ("kc general", "k c general", "k.c. general"), "Malleswaram", 13.0035, 77.5700),
    ("Government Hospital, Yelahanka", ("yelahanka government", "yelahanka hospital"), "Yelahanka", 13.1000, 77.5960),
    ("Sanjay Gandhi Accident Trauma and Orthopaedic Hospital", ("sanjay gandhi", "sanjay gandhi hospital"), "Jayanagar", 12.9183, 77.5887),
    ("Suguna Hospital, Rajajinagar", ("suguna",), "Rajajinagar", 12.9910, 77.5520),
    ("Vydehi Institute of Medical Sciences, Whitefield", ("vydehi",), "Whitefield", 12.9764, 77.7370),
    ("Kempegowda Institute of Medical Sciences Hospital, V.V. Puram", ("kims", "kempegowda institute"), "V.V. Puram", 12.9458, 77.5720),
    ("Command Hospital Air Force, Old Airport Road", ("command hospital",), "Old Airport Road", 12.9610, 77.6370),
    ("Bangalore Hospital, Jayanagar", ("bangalore hospital",), "Jayanagar", 12.9291, 77.5848),
    ("Lakeside Hospital and Research Centre, Ulsoor", ("lakeside",), "Ulsoor", 12.9790, 77.6260),
    ("Shanthi Hospital, Rajajinagar", ("shanthi",), "Rajajinagar", 12.9930, 77.5560),
    ("Shreya Hospital, Yeshwanthpur", ("shreya",), "Yeshwanthpur", 13.0280, 77.5420),
]


def hospital_rows():
    """(name, address, latitude, longitude) for every listed hospital."""
    return [(n, f"{area}, Bengaluru", lat, lon) for n, _aliases, area, lat, lon in HOSPITALS]
