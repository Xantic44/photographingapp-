# Del A och Del B i samma fil
# Inlamningsuppgift programmering

import random


# -------- DEL A: Gissa talet --------

def del_a_guess_number():
    # slumpa ett hemligt tal mellan 1-200
    hemligt_tal = random.randint(1, 200)
    max_forsok = 10
    gissningar = []
    
    print('\nValkommen till Gissa Talet!')
    print('Jag har tankt pa ett tal mellan 1 och 200.')
    print(f'Du har {max_forsok} forsok pa dig. Lycka till!\n')
    
    forsok = 1
    while forsok <= max_forsok:
        # las in gissning fran anvandaren
        svar = input(f'Forsok {forsok}: ').strip()
        
        # kolla om det ar tomt
        if svar == '':
            print('Fel: du maste skriva nagot!\n')
            continue
        
        # kolla om det ar ett tal
        try:
            gissning = int(svar)
        except ValueError:
            print('Fel: du maste skriva ett heltal!\n')
            continue
        
        # kolla om talet ar inom intervallet
        if gissning < 1 or gissning > 200:
            print('Fel: talet maste vara mellan 1 och 200!\n')
            continue
        
        # spara gissningen
        gissningar.append(gissning)
        
        # jamfor med hemliga talet
        if gissning < hemligt_tal:
            print('For lagt!\n')
        elif gissning > hemligt_tal:
            print('For hogt!\n')
        else:
            print(f'RATT! Talet var {hemligt_tal}. Du klarade det pa {forsok} forsok!\n')
            break
        
        forsok = forsok + 1
    
    # om man inte gissade ratt
    if gissning != hemligt_tal:
        print(f'Tyvarr, du fick slut pa forsok. Talet var {hemligt_tal}.\n')
    
    # skriv ut statistik
    print('--- Statistik ---')
    print(f'Antal gissningar: {len(gissningar)}')
    
    if len(gissningar) > 0:
        # skriv ut alla gissningar
        print('Dina gissningar: ', end='')
        for i in range(len(gissningar)):
            if i == len(gissningar) - 1:
                print(gissningar[i])
            else:
                print(gissningar[i], end=', ')
        
        # hitta basta och samsta gissning
        basta = gissningar[0]
        basta_avstand = abs(gissningar[0] - hemligt_tal)
        samsta = gissningar[0]
        samsta_avstand = abs(gissningar[0] - hemligt_tal)
        
        for g in gissningar:
            avstand = abs(g - hemligt_tal)
            if avstand < basta_avstand:
                basta = g
                basta_avstand = avstand
            if avstand > samsta_avstand:
                samsta = g
                samsta_avstand = avstand
        
        print(f'Basta gissning: {basta} (avstand: {basta_avstand})')
        print(f'Samsta gissning: {samsta} (avstand: {samsta_avstand})')
    else:
        print('Du gjorde inga gissningar.')
    print()


# -------- DEL B: Lotto --------

def slumpa_lottotal():
    # slumpa 7 unika tal mellan 1-50
    lotto = []
    while len(lotto) < 7:
        tal = random.randint(1, 50)
        # kolla att talet inte redan finns
        if tal not in lotto:
            lotto.append(tal)
    return lotto


def del_b_lotto():
    # slumpa lottotalen
    lotto_tal = slumpa_lottotal()
    
    # lista for anvandarens tal
    mina_tal = []
    
    print('\nValkommen till Lotto!')
    print('Ange 7 unika tal mellan 1 och 50:\n')
    
    nummer = 1
    while nummer <= 7:
        svar = input(f'Tal {nummer}: ').strip()
        
        # kolla om tomt
        if svar == '':
            print('Fel: du maste ange ett tal!')
            continue
        
        # kolla om det ar ett heltal
        try:
            tal = int(svar)
        except ValueError:
            print('Fel: du maste ange ett heltal!')
            continue
        
        # kolla intervall
        if tal < 1 or tal > 50:
            print('Fel: talet maste vara mellan 1 och 50!')
            continue
        
        # kolla dubbletter
        if tal in mina_tal:
            print('Fel: du har redan angett det talet!')
            continue
        
        # allt ok, lagg till talet
        mina_tal.append(tal)
        nummer = nummer + 1
    
    # sortera listorna
    mina_tal.sort()
    lotto_tal.sort()
    
    # rakna hur manga ratt
    ratt_tal = []
    for t in mina_tal:
        if t in lotto_tal:
            ratt_tal.append(t)
    
    # skriv ut resultat
    print('\n--- Resultat ---')
    
    print('Dina tal: ', end='')
    for i in range(len(mina_tal)):
        if i == len(mina_tal) - 1:
            print(mina_tal[i])
        else:
            print(mina_tal[i], end=', ')
    
    print('Lottotalen: ', end='')
    for i in range(len(lotto_tal)):
        if i == len(lotto_tal) - 1:
            print(lotto_tal[i])
        else:
            print(lotto_tal[i], end=', ')
    
    print()
    print(f'Antal ratt: {len(ratt_tal)}')
    
    if len(ratt_tal) > 0:
        print('Ratt tal: ', end='')
        for i in range(len(ratt_tal)):
            if i == len(ratt_tal) - 1:
                print(ratt_tal[i])
            else:
                print(ratt_tal[i], end=', ')
    else:
        print('Inga ratt tyvarr!')
    print()


# -------- HUVUDPROGRAM --------

def main():
    print('=== Inlamningsuppgift ===')
    
    while True:
        print('Valj vad du vill gora:')
        print('1. Gissa talet (Del A)')
        print('2. Lotto (Del B)')
        print('3. Avsluta')
        
        val = input('Ditt val (1-3): ').strip()
        print()
        
        if val == '1':
            del_a_guess_number()
        elif val == '2':
            del_b_lotto()
        elif val == '3':
            print('Hej da!')
            break
        else:
            print('Fel: valj 1, 2 eller 3!\n')


# kor programmet
if __name__ == '__main__':
    main()
