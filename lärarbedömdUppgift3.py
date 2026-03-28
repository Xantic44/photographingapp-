# Kontaktregister - Uppgift 3 -- svengelska syftet är att alla trots språk ska kunna använda koden
# Namn: [Ditt namn]
# Datum: 2026-03-04

# Listor for att spara kontakter
namn = []
telefon = []
alder = []


# Funktion 1: Visa menyn
def visa_meny():
    print("\n--- KONTAKTREGISTER ---")
    print("1. Lagg till kontakt")
    print("2. Visa alla kontakter")
    print("3. Sok kontakt")
    print("4. Ta bort kontakt")
    print("5. Visa statistik")
    print("6. Avsluta")
    val = input("Valj (1-6): ")
    return val


# Funktion 2: Lagg till kontakt
def lagg_till():
    print("\n-- Lagg till ny kontakt --")
    
    # Namn - maste vara minst 2 tecken
    while True:
        n = input("Namn: ")
        if len(n) >= 2:
            break
        print("Fel: Namnet maste vara minst 2 tecken!")
    
    # Telefon - maste vara exakt 10 siffror
    while True:
        t = input("Telefonnummer: ")
        # Rakna antalet siffror
        antal_siffror = 0
        for c in t:
            if c in "0123456789":
                antal_siffror = antal_siffror + 1
        if antal_siffror == 10:
            break
        print("Fel: Telefonnummer maste vara 10 siffror!")
    
    # Alder - maste vara mellan 13-80 ar
    while True:
        a = input("Alder: ")
        if a.isdigit() and 13 <= int(a) <= 80:
            break
        print("Fel: Ange en giltig alder (13-80)!")
    
    # Lagg till i listorna
    namn.append(n)
    telefon.append(t)
    alder.append(int(a))
    
    print("Kontakten sparades!")


# Funktion 3: Visa alla kontakter
def visa_alla():
    print("\n-- Alla kontakter --")
    
    if len(namn) == 0:
        print("Inga kontakter sparade.")
        return
    
    print("Nr   Namn                 Telefon          Alder")
    print("-" * 50)
    
    for i in range(len(namn)):
        print(str(i+1) + ".   " + namn[i] + "   " + telefon[i] + "   " + str(alder[i]))
    
    print("-" * 50)
    print("Totalt:", len(namn), "kontakter")


# Funktion 4: Sok kontakt
def sok():
    print("\n-- Sok kontakt --")
    
    if len(namn) == 0:
        print("Inga kontakter att soka i.")
        return
    
    sokord = input("Ange sokord: ").lower()
    
    # Sok igenom listan
    hittade = 0
    for i in range(len(namn)):
        if sokord in namn[i].lower() or sokord in telefon[i]:
            print("Hittade:", namn[i], "-", telefon[i], "-", alder[i], "ar")
            hittade = hittade + 1
    
    if hittade == 0:
        print("Ingen kontakt hittades.")
    else:
        print("Hittade", hittade, "kontakt(er).")


# Funktion 5: Ta bort kontakt (Niva 2)
def ta_bort():
    print("\n-- Ta bort kontakt --")
    
    if len(namn) == 0:
        print("Inga kontakter att ta bort.")
        return
    
    # Visa alla forst
    for i in range(len(namn)):
        print(str(i+1) + ". " + namn[i])
    
    val = input("Vilken vill du ta bort? (nummer): ")
    
    # Kolla om det ar ett giltigt nummer
    if not val.isdigit():
        print("Fel: Du maste skriva ett nummer!")
        return
    
    index = int(val) - 1
    
    if index < 0 or index >= len(namn):
        print("Fel: Det numret finns inte!")
        return
    
    # Ta bort fran alla listor
    borttagen = namn[index]
    namn.pop(index)
    telefon.pop(index)
    alder.pop(index)
    
    print(borttagen, "har tagits bort.")


# Funktion 6: Visa statistik (Niva 3)
def statistik():
    print("\n-- Statistik --")
    
    if len(namn) == 0:
        print("Inga kontakter, ingen statistik.")
        return
    
    # Statistik 1: Langsta namnet (loop + jamforelse)
    langst = namn[0]
    for n in namn:
        if len(n) > len(langst):
            langst = n
    
    # Statistik 2: Genomsnittlig alder (loop + summering)
    summa = 0
    for a in alder:
        summa = summa + a
    medel = summa / len(alder)
    
    # Statistik 3: Antal over 30 ar (loop + villkor)
    antal_over_30 = 0
    for a in alder:
        if a > 30:
            antal_over_30 = antal_over_30 + 1
    
    # Statistik 4: Yngst och aldst
    yngst = alder[0]
    aldst = alder[0]
    for a in alder:
        if a < yngst:
            yngst = a
        if a > aldst:
            aldst = a
    
    # Skriv ut
    print("Antal kontakter:", len(namn))
    print("Langsta namnet:", langst, "(" + str(len(langst)) + " tecken)")
    print("Medelalder:", round(medel, 1), "ar")
    print("Antal over 30 ar:", antal_over_30)
    print("Yngst:", yngst, "ar")
    print("Aldst:", aldst, "ar")


# Huvudprogram
def main():
    print("Valkommen till kontaktregistret!")
    
    while True:
        val = visa_meny()
        
        if val == "1":
            lagg_till()
        elif val == "2":
            visa_alla()
        elif val == "3":
            sok()
        elif val == "4":
            ta_bort()
        elif val == "5":
            statistik()
        elif val == "6":
            print("Hejda!")
            break
        else:
            print("Fel val, forsok igen.")


# Starta programmet
main()


"""
TESTFALL:

1. Lagg till giltig kontakt
   Input: Anna, 0701234567, 25
   Resultat: OK, kontakten sparas

2. Lagg till med for kort namn
   Input: A
   Resultat: Felmeddelande, ber om nytt namn

3. Ta bort kontakt som inte finns
   Input: nummer 99 nar bara 2 finns
   Resultat: Felmeddelande

4. Sok i tomt register
   Input: soka utan kontakter
   Resultat: Meddelande att det ar tomt

5. Statistik med kontakter
   Input: 3 kontakter (25, 42, 18 ar)
   Resultat: Medel 28.3, over 30: 1


REFLEKTION OM ETIK OCH INTEGRITET:

Telefonummer och alder ar personuppgifter som skyddas av GDPR.
I mitt program:
- Data forsvinner nar programmet stangs (bra for integritet)
- Man kan ta bort sina uppgifter (ratt till radering)
- Man kan se sina uppgifter (ratt till insyn)
-


Om programmet skulle spara data till fil maste man:
- Fraga om samtycke forst
- Inte dela data med andra
- Ha nagon form av skydd

Jag har tankt pa att inte lagra mer an nodvandigt
(endast namn, telefon och alder). 

detta tog mig ca 8 dagar totalt. det gillar jag men jag har använt mig av AI för slutligen testfall och "polish" koden jag har skrivit och en före / efter är minimal skillnad då det gällade att gå igenom koden och markera ev. fel
tanken att ansluta en debugger fanns där dock kanske lite overkill så jag lät bli att använda en debbugger som körs när man .py filen 
har en liknande live debugger i min discord bot applikation jag gjorde i JS och ny python, VS-code har en bra debugger när man kör manuellt.
det finns rum för mycket förbättringar i koden och i appen i sjig dock är frågan hur mycket man vill investera i detta egentligen och det är så mycket mer loops samt for i i python än JS
JS jämfört med python kan vara enklare att skriva och använda sig av i många fall dock tror jag python har en mer effektiv användning i många mer appar och produkter.
det pendlas mkt mellan oae och öäå och då gället det att förstå sig på redan i tidig fas i programmering som jag hade problem med inom JS var att andra kunde inte köra koden som jag hade eller lämna feedback 
för de flesta har inte nordiska tangenter eller talar nordiska. en blandning för ens egna reflektion går bra anser jag men i koden får det vara neutralt anser jag
jag trodde aldrig att jag skulle använda mig av etik, hållbarhet i kod men det är viktigt antar jag nu när "mass surveilance" är så enkelt tillgägnligt och vi alla är utsatta till en viss grad
minska batteri eller elförbrukning är svårt och jag tror inte att jag kan utvecklas där sålänge man inte är kanske en stor team som microsoft? 
givetvis kan en app eller hemsida man gör förbättras till en längre livslängd trots vad den körs på men att minska bakgrundsprocesser eller minska elektricitet 
är näst intill bara inte möjligt då beroende på webbläsare,OP-system och dylikt påverkar vad som visas i skärmen och skriva kod som kan optimizera detta kan även leda till att man skriver kod som ökar
bakgrundsprocesser eller elförbrukning så det är en svår balansgång.
"""
