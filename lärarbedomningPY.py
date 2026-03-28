"Del A – Temperaturkonverterare"
# Skriv en funktion som konverterar Celsius till Fahrenheit. Formeln är: F = C * 9/5 + 32
def celsius_to_fahrenheit(c):
    return c * 9 / 5 + 32


user_input = input("Skriv in temperatur i Celsius: ")

try:
    celsius = float(user_input)
    fahrenheit = celsius_to_fahrenheit(celsius)

    # 1 decimal
    print(f"{celsius:.1f}°C motsvarar {fahrenheit:.1f}°F.")
except ValueError:
    print("Fel: Du måste skriva ett tal, t.ex. 20 eller 20.5.")



    "Del B Sparsimulator (Python)"
    "namn (text),månadsbelopp(tal),månader(heltal),ränta %(tal)"
    "insatt=månadsbelopp*månader,med_ränta=insatt *(1 + ränta/100)????"
    "ehhhhhh vafan hjälppppppppppppppppp"
def read_float(prompt):
    while True:
        user_input = input(prompt)
        try:
            return float(user_input)
        except ValueError:
            print("Fel: skriv ett tal, t.ex. 1500 eller 3.5.")
  
  
  
 
def read_int(prompt):
    while True:
        user_input = input(prompt)
        try:
            value = int(user_input)
            if value < 0:
                print("Fel: skriv ett heltal som är 0 eller större.")
            else:
                return value
        except ValueError:
            print("Fel: skriv ett heltal, t.ex. 24.")
 
 
 
 
 
 
 
 
 
 


def calculate_savings(monthly_amount, months, interest_percent):
    deposited = monthly_amount * months
    interest_decimal = interest_percent / 100
    total_with_interest = deposited * (1 + interest_decimal)  #DETTA ÄR TYDLIGEN FÖRENKLAT I PYTHON?!
    return deposited, total_with_interest

Name = input("Skriv in ditt namn: ")
monthly_amount = read_float("Skriv in ditt månadsbelopp: ")
months = read_int("Skriv in antal månader: ")
interest_percent = read_float("Skriv in räntan i procent: ")
deposited, total_with_interest = calculate_savings(monthly_amount, months, interest_percent)
print("\n--- Resultat---")
print(f"Totalt insatt belopp:{round(deposited, 1)} kr")
print(f"Totalt belopp inklusive ränta: {round(total_with_interest, 1)} kr")

"jag har ont i huvet."
print("\n --- Förklaring ---")
print(
    f"{Name}, du sparar {round(monthly_amount, 1)} kr varje månad i {months} månader, "
 f"vilket ger totalt {round(deposited, 1)} kr utan ränta. "
f"med {round(interest_percent, 1)}% ränta, växer ditt sparande till {round(total_with_interest, 1)} kr"
)  
  

"logg"
"trots kunna javascript, html, css så har jag fortfarande inte riktigt förtstårr hur python fungerar och finner mig själv med syntaxen bråka ibland"
"detta var en bra uppgift med jag ska vara ärlig och säga att jag hade svårt med spar simulatorn och fastnade mycket, trots YT och mina VS code extensions så var det svårt att förstå"
"vad jag höll på med men sålänge det fungerar så är jag nöjd om jag ska vara ärlig. detta tog mig förseningar men det var svårt att göra detta från huvvet utan extern hjälp"
"bonus poäng! hoppas på flera coola uppgifter i framtiden, det var kul att göra detta och jag lärde mig mycket, även om det var svårt ibland"