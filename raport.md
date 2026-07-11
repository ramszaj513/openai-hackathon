# Raport produktowy: pełny flow Agent Commerce Gateway

## 1. Streszczenie

Agent Commerce Gateway to doświadczenie zakupowe, w którym użytkownik opisuje rezultat, jaki chce osiągnąć, a agent prowadzi transakcję od rozpoznania potrzeby aż do obsługi zamówienia po zakupie. Produkt nie jest klasycznym sklepem internetowym ani chatbotem rekomendującym produkty. Jego istotą jest bezpieczna warstwa transakcyjna łącząca intencję użytkownika, ofertę sprzedawcy, świadomą zgodę, płatność, zamówienie i późniejszą obsługę.

Główna obietnica produktu brzmi:

> Użytkownik mówi, czego potrzebuje i na jakich warunkach. Agent wyszukuje realnie dostępne opcje, wybiera odpowiednią, prosi o zgodę na dokładną transakcję, kupuje, monitoruje realizację i pomaga rozwiązać problem po zakupie.

Całość można zapisać jako:

```text
discover → decide → approve → purchase → track → resolve
```

Najważniejsze rozróżnienie dotyczy odpowiedzialności. Agent rozumie język użytkownika, ocenia znaczenie ofert i wyjaśnia wybór. Nie jest jednak źródłem prawdy o cenie, dostępności, zgodzie, płatności ani stanie zamówienia. Te informacje pochodzą z autorytatywnych źródeł i są sprawdzane niezależnie od deklaracji agenta.

## 2. Wartość biznesowa

W tradycyjnym e-commerce użytkownik sam wykonuje większość pracy: wyszukuje, otwiera produkty, porównuje parametry, sprawdza warunki dostawy, przechodzi przez checkout, monitoruje przesyłkę i kontaktuje się ze sklepem w przypadku problemu. Tutaj ciężar operacyjny przejmuje agent.

Wartość produktu nie polega wyłącznie na szybszym znalezieniu produktu. Polega na domknięciu całego zadania przy zachowaniu kontroli użytkownika. Dzięki temu agent może stać się operatorem transakcji, a nie tylko doradcą.

Produkt może docelowo tworzyć wartość dla kilku grup:

- użytkownik oszczędza czas i nie musi poznawać procesu zakupowego każdego sprzedawcy;
- sprzedawca udostępnia ofertę agentom w ustrukturyzowany sposób i otrzymuje poprawnie przygotowaną transakcję;
- dostawca płatności obsługuje precyzyjnie ograniczoną zgodę zamiast ogólnego dostępu do pieniędzy;
- operator platformy tworzy wspólną warstwę zaufania, audytu i obsługi cyklu życia zamówienia;
- biznes może obsługiwać zakupy inicjowane przez różne interfejsy agentowe bez budowania osobnego procesu dla każdego z nich.

## 3. Główni uczestnicy doświadczenia

### Użytkownik

Formułuje potrzebę, odpowiada na pytania doprecyzowujące, zatwierdza dokładną transakcję i może później anulować zamówienie albo rozpocząć zwrot. Użytkownik nie musi zarządzać technicznym przebiegiem zakupu, ale pozostaje właścicielem decyzji o wydaniu pieniędzy.

### Agent zakupowy

Rozumie intencję, oddziela wymagania twarde od preferencji, porównuje semantycznie produkty, uzasadnia wybór i koordynuje kolejne kroki. Agent reprezentuje cel użytkownika, lecz nie może sam ustanowić ceny, potwierdzić zgody ani uznać zamówienia za złożone.

### Sprzedawca

Jest źródłem prawdy o produkcie, wariancie, cenie, stanie magazynowym, dostawie, warunkach zwrotu, checkoutcie i zamówieniu. To sprzedawca potwierdza, że dana transakcja rzeczywiście istnieje.

### Warstwa zgody i polityki

Sprawdza, czy agent ma prawo wykonać transakcję. Może wymagać jednorazowej zgody użytkownika lub rozpoznać wcześniej nadany mandat zakupowy. Zgoda zawsze dotyczy dokładnej wersji checkoutu, a nie ogólnego polecenia „kup monitor”.

### Warstwa płatności

Rezerwuje i pobiera dokładną zatwierdzoną kwotę. Nie udostępnia agentowi ani interfejsowi użytkownika danych pozwalających na dowolne kolejne obciążenia.

### Interfejs rozmowy

Jest powierzchnią sterowania, zgody i obserwowalności. Pokazuje, co agent zrozumiał, co aktualnie robi, dlaczego wybrał dany produkt, jaka transakcja czeka na zgodę oraz co dzieje się z zamówieniem. Nie jest źródłem prawdy o pieniądzach ani stanie transakcji.

## 4. Punkt wejścia i model interakcji

Użytkownik rozpoczyna w pojedynczym widoku rozmowy. Może wpisać dowolną potrzebę zakupową albo użyć gotowego przykładu demonstracyjnego. Kanoniczny scenariusz brzmi:

> Kup monitor kompatybilny z Makiem za maksymalnie 1200 PLN, z dostawą jutro i co najmniej 30-dniowym prawem zwrotu. Kup go, jeśli jesteś pewny wyboru.

Interfejs od początku komunikuje trzy elementy obietnicy:

1. agent porówna opcje;
2. agent wyjaśni wybór;
3. użytkownik zatwierdzi dokładną kwotę przed zakupem.

Po wysłaniu wiadomości użytkownik od razu widzi ją w rozmowie. Transakcja otrzymuje własną tożsamość i pojawia się na liście konwersacji. Dalsza praca odbywa się w tle, więc użytkownik może obserwować postęp lub przełączyć się do innego zadania. Powrót do wcześniejszej rozmowy odtwarza jej aktualny stan, a nie tylko historyczny zrzut interfejsu.

To ważna cecha doświadczenia: zakup jest traktowany jak długotrwałe zadanie, do którego można wrócić, a nie jak jednorazowa odpowiedź chatbota.

## 5. Szczegółowy przebieg end-to-end

### Etap 1: przechwycenie intencji

Pierwsza wiadomość nie jest jeszcze zgodą na płatność. Jest opisem celu. Agent zamienia język naturalny na uporządkowaną intencję zakupową, obejmującą między innymi:

- rodzaj produktu;
- liczbę sztuk;
- maksymalny budżet i walutę;
- wymagane właściwości lub kompatybilność;
- najpóźniejszy akceptowalny termin dostawy;
- minimalne warunki zwrotu;
- informację, czy agent może kontynuować, gdy jest wystarczająco pewny.

W scenariuszu monitora agent rozumie, że kompatybilność z Makiem, budżet, dostawa jutro i minimum 30 dni na zwrot są warunkami koniecznymi, a nie luźnymi preferencjami.

#### Gdy brakuje informacji

Jeżeli brakuje danych potrzebnych do odpowiedzialnego działania, transakcja przechodzi do stanu wymagającego doprecyzowania. Agent zadaje konkretne pytanie, a pole rozmowy pozostaje dostępne. Odpowiedź użytkownika kontynuuje historię rozmowy i uruchamia ponowną interpretację pełnej potrzeby.

Z punktu widzenia UX jest to moment, w którym system powinien jasno pokazać różnicę między:

- pytaniem opcjonalnym, które poprawi rekomendację;
- pytaniem blokującym, bez którego nie można bezpiecznie kontynuować;
- brakiem produktu na rynku lub w katalogu.

### Etap 2: szerokie odkrywanie ofert

Po zrozumieniu intencji system pobiera aktualne oferty sprzedawcy. Oferta jest czymś więcej niż kartą produktu: zawiera wersję, dostępność, cenę jednostkową, wariant, opcje dostawy, termin ważności i warunki zwrotu.

Wyszukiwanie jest celowo szerokie. System nie zakłada, że użytkownik i sprzedawca używają tych samych nazw cech. Przykładowo wymaganie „kompatybilny z Makiem” może odpowiadać opisowi „zgodny z macOS” albo cesze kompatybilności zapisanej w danych produktu w języku sprzedawcy.

### Etap 3: obiektywna kwalifikacja kandydatów

Zanim agent oceni znaczenie produktu, system usuwa oferty, które obiektywnie nie mogą spełnić transakcji. Sprawdzane są:

- dostępna ilość;
- waluta;
- budżet wraz z wybraną dostawą;
- możliwość dostarczenia w wymaganym terminie;
- minimalne prawo do zwrotu.

Te warunki nie są pozostawione interpretacji językowej. Przykładowo system nie pyta agenta, czy 1149 PLN mieści się w budżecie 1200 PLN. To jednoznaczny warunek transakcyjny.

### Etap 4: semantyczne porównanie produktów

Agent otrzymuje wszystkich kandydatów, którzy przeszli obiektywne warunki, wraz z ich nazwą, kategorią, opisem, wariantem i cechami. Następnie ocenia każdy produkt osobno względem znaczenia potrzeby użytkownika.

Dla każdego kandydata agent określa:

- czy produkt jest dopasowaniem;
- poziom pewności;
- krótkie uzasadnienie oparte na danych oferty.

W scenariuszu demonstracyjnym agent porównuje między innymi dwa monitory:

- monitor gamingowy zostaje odrzucony, ponieważ dane oferty wprost mówią o braku wspieranej kompatybilności z Makiem;
- monitor StudioView zostaje uznany za dopasowanie, ponieważ opis wskazuje kompatybilność z macOS, a dane produktu ją potwierdzają.

Jeśli więcej niż jeden produkt zostanie uznany za dopasowanie, preferowany jest wynik o najwyższej pewności, a przy takim samym poziomie pewności korzystniejsza cenowo kwalifikująca się oferta.

Agent nie może wybrać produktu, którego nie było wśród otrzymanych kandydatów. Nie może też ominąć odrzucenia wynikającego z braku stocku, przekroczonego budżetu, spóźnionej dostawy lub zbyt krótkiego zwrotu.

#### Gdy nic nie pasuje

Jeżeli żadna oferta nie spełnia obiektywnych warunków albo agent nie znajduje semantycznego dopasowania, transakcja kończy się czytelnym stanem „brak dopasowania”. Jest to prawidłowy rezultat wyszukiwania, a nie techniczny błąd.

Użytkownik widzi informację, że wyszukiwanie się zakończyło i dlaczego nie dokonano wyboru. Obecne doświadczenie zatrzymuje się w tym miejscu; naturalnym obszarem dalszego projektowania są działania następcze, takie jak poluzowanie jednego warunku, zapisanie alertu, rozszerzenie listy sprzedawców lub zaproponowanie bezpiecznej alternatywy.

### Etap 5: prezentacja wyboru

Po znalezieniu dopasowania interfejs przedstawia:

- podsumowanie zrozumianych ograniczeń;
- nazwę, markę i wariant wybranego produktu;
- cenę sprzedawcy;
- termin dostawy;
- długość okresu zwrotu;
- procent pewności;
- krótkie uzasadnienie wyboru.

To moment „decyzji”, ale jeszcze nie moment „zakupu”. Wybrana oferta nadal może się zmienić lub wygasnąć przed utworzeniem checkoutu.

### Etap 6: autorytatywny checkout

Po wyborze sprzedawca ponownie sprawdza produkt i tworzy checkout. Checkout jest właściwą propozycją transakcji, a nie prostym przepisaniem ceny widocznej w wynikach wyszukiwania.

Sprzedawca określa w nim:

- dokładny produkt, wariant i ilość;
- subtotal, rabaty, dostawę, podatki, opłaty i sumę końcową;
- wybraną metodę oraz obietnicę dostawy;
- warunki anulowania i zwrotu;
- czas ważności;
- aktualną wersję transakcji;
- ewentualną tymczasową rezerwację towaru.

Checkout ma numer wersji. Każda istotna zmiana tworzy nową rzeczywistość transakcyjną. Dzięki temu późniejsza zgoda użytkownika nie może zostać przypadkowo użyta do innej ceny, innego wariantu lub innych warunków.

### Etap 7: dokładna zgoda użytkownika

Jeśli transakcja wymaga zgody, interfejs pokazuje kartę zatwierdzenia. Użytkownik widzi na niej:

- produkt i ilość;
- cenę pozycji;
- koszt oraz termin dostawy;
- podatki;
- dokładną sumę;
- warunki zwrotu;
- sprzedawcę;
- wersję checkoutu;
- termin wygaśnięcia;
- identyfikator zabezpieczający treść propozycji.

Użytkownik musi świadomie zaznaczyć zgodę i uruchomić akcję „Approve & place order”. Zgoda nie dotyczy ogólnego celu zakupowego. Dotyczy dokładnej, niezmiennej propozycji.

Jeżeli po zgodzie zmieni się produkt, ilość, cena, waluta, sprzedawca, dostawa lub warunki zwrotu, poprzednia zgoda przestaje obowiązywać. System powinien wrócić do użytkownika z nową propozycją zamiast automatycznie kontynuować.

#### Mandat zakupowy

Produkt przewiduje również możliwość wcześniejszego nadania agentowi ograniczonego mandatu, na przykład:

> Agent może kupować monitory u wskazanych sprzedawców do 1200 PLN, pod warunkiem dostawy do określonej daty i minimum 30 dni na zwrot.

Jeżeli checkout dokładnie mieści się w takim mandacie, transakcja może zostać zatwierdzona automatycznie. Mandat ma ograniczenia kwotowe, zakres sprzedawców lub kategorii, okres ważności oraz możliwość odwołania. Rezerwuje także dostępny limit, aby kilka równoczesnych zakupów nie przekroczyło ustalonego budżetu.

W obecnym interfejsie główny nacisk położony jest na zgodę jednorazową; projektowanie i zarządzanie mandatami jest znaczącym obszarem dalszego rozwoju doświadczenia.

### Etap 8: autoryzacja płatności

Po ważnej zgodzie system uzyskuje jednorazowe uprawnienie do obciążenia dokładnie tej transakcji. Uprawnienie jest związane z:

- konkretnym checkoutem i jego wersją;
- konkretnym sprzedawcą;
- dokładną kwotą i walutą;
- konkretną zgodą użytkownika;
- krótkim terminem ważności.

Autoryzacja oznacza, że środki mogą zostać pobrane, ale nie oznacza jeszcze, że istnieje zamówienie. Interfejs nie powinien w tym momencie komunikować sukcesu zakupu.

Jeżeli płatność zostanie odrzucona, zamówienie nie może zostać utworzone jako opłacone. Użytkownik otrzymuje stabilną i bezpieczną informację o niepowodzeniu.

### Etap 9: utworzenie zamówienia

Sprzedawca otrzymuje potwierdzenie zgody i ograniczoną autoryzację płatności. Ponownie sprawdza checkout, stock, wersję, cenę, walutę i ważność wszystkich uprawnień.

Zakup jest uznany za udany dopiero wtedy, gdy sprzedawca zwróci autorytatywne potwierdzenie zamówienia z identyfikatorem zamówienia. Dopiero po takim potwierdzeniu płatność zostaje przechwycona.

Kolejność ma znaczenie:

```text
ważna zgoda
→ autoryzacja płatności
→ potwierdzenie zamówienia przez sprzedawcę
→ pobranie płatności
→ potwierdzenie dla użytkownika
```

Interfejs pokazuje kartę zamówienia z numerem zamówienia, statusem płatności i terminem dostawy. Komunikat sukcesu oznacza rzeczywiście utworzone zamówienie, a nie tylko pozytywną odpowiedź agenta.

### Etap 10: śledzenie realizacji

Po zakupie agent pozostaje odpowiedzialny za zadanie. Transakcja przechodzi przez kolejne etapy realizacji, takie jak:

```text
potwierdzone → przetwarzane → wysłane → dostarczone
```

Interfejs pokazuje aktywność w czasie rzeczywistym. Użytkownik może otworzyć szczegóły przebiegu i zobaczyć kolejne fazy: rozumienie intencji, wyszukiwanie, wybór, checkout, zgodę, płatność, zamówienie, realizację i rozwiązanie problemu.

Oś aktywności jest wyjaśnieniem, a nie alternatywnym źródłem stanu. Jeśli opis aktywności i aktualny stan zamówienia byłyby rozbieżne, ważniejszy jest aktualny stan potwierdzony przez odpowiedzialną stronę.

Użytkownik może zamknąć lub zmienić rozmowę, a później wrócić do transakcji. Lista rozmów zachowuje bezpieczne podsumowania, natomiast bieżący stan jest ponownie pobierany ze źródła prawdy.

### Etap 11: anulowanie przed realizacją

Dopóki stan zamówienia pozwala na anulowanie, interfejs pokazuje odpowiednią akcję. Po jej uruchomieniu sprzedawca ponownie ocenia kwalifikację na podstawie aktualnego etapu realizacji.

Jeżeli anulowanie jest możliwe:

- zamówienie przechodzi do stanu anulowanego;
- jeśli środki były tylko zarezerwowane, rezerwacja zostaje zwolniona;
- jeśli środki zostały pobrane, rozpoczyna się zwrot;
- wynik pozostaje powiązany z pierwotną zgodą, płatnością i zamówieniem.

Jeżeli realizacja zaszła za daleko, system nie powinien obiecywać anulowania. Powinien wyjaśnić aktualną kwalifikację i skierować użytkownika do właściwej ścieżki, na przykład zwrotu po dostawie.

### Etap 12: zwrot po dostawie

Po dostarczeniu produktu interfejs udostępnia formularz zwrotu. Użytkownik podaje powód, a system określa produkty i ilości objęte żądaniem.

Sprzedawca sprawdza:

- czy zamówienie zostało dostarczone;
- czy produkt jest zwrotny;
- czy nie minął termin;
- czy żądana ilość jest poprawna;
- jaka kwota podlega refundacji.

Prawidłowy zwrot pozostaje powiązany z pierwotnym zamówieniem i płatnością. Interfejs pokazuje zakończenie rozwiązania oraz zwróconą kwotę. Biznesowo istotne jest, że agent nie znika po kliknięciu „kup”, ale domyka również negatywny scenariusz.

## 6. Odporność i ścieżki wyjątków

### Zmiana ceny lub warunków

Jeżeli oferta lub checkout ulegnie istotnej zmianie, wcześniejsza zgoda nie może zostać wykorzystana. Użytkownik powinien zobaczyć, co się zmieniło, i ponownie zatwierdzić nową propozycję.

### Brak stocku

Produkt bez wymaganej ilości nie może przejść do checkoutu. Jeśli stock zniknie pomiędzy wyszukiwaniem a finalizacją, system zatrzymuje transakcję zamiast zastępować produkt bez zgody.

### Odrzucona płatność

Odrzucenie płatności nie tworzy opłaconego zamówienia. Doświadczenie powinno pozwolić użytkownikowi zrozumieć, że problem dotyczy płatności, a nie doboru produktu.

### Niejasny rezultat połączenia

Najbardziej ryzykowny przypadek występuje wtedy, gdy system wysłał finalizację, ale nie otrzymał odpowiedzi. Nie wiadomo wtedy, czy zamówienie powstało.

System nie powtarza ślepo operacji. Najpierw pyta sprzedawcę o zamówienie powiązane z checkoutem:

- jeśli zamówienie istnieje, odzyskuje je i kończy istniejącą płatność;
- jeśli zamówienie nie istnieje, zwalnia autoryzację płatniczą;
- jeśli nadal nie można ustalić prawdy, pokazuje stan wymagający odzyskania zamiast fałszywego sukcesu.

### Ponowienie tej samej akcji

Kliknięcie drugi raz, odświeżenie strony lub ponowienie po problemie sieciowym nie powinno tworzyć drugiego zamówienia, drugiej płatności, drugiego anulowania ani podwójnego zwrotu. Powtórzona identyczna akcja prowadzi do tego samego rezultatu. Próba użycia tego samego żądania do innej treści jest traktowana jako konflikt.

### Utrata połączenia z aplikacją

Interfejs rozpoznaje niedostępność usługi i komunikuje problem. Długotrwała praca agenta nie jest automatycznie uznawana za porażkę; użytkownik może wrócić do transakcji i odświeżyć jej stan.

## 7. Co użytkownik widzi w poszczególnych stanach

| Sytuacja | Główny komunikat | Dostępna akcja |
|---|---|---|
| Brak rozpoczętej transakcji | Zaproszenie do opisania potrzeby | Wpisanie prośby lub użycie przykładu |
| Agent pracuje | Animacja oraz aktywność wyszukiwania | Obserwowanie lub przełączenie rozmowy |
| Brakuje danych | Konkretne pytanie doprecyzowujące | Odpowiedź w tym samym composerze |
| Brak dopasowania | Wyszukiwanie zakończone bez odpowiedniej oferty | Obecnie głównie rozpoczęcie nowej próby |
| Znaleziono produkt | Podsumowanie wymagań, produkt i uzasadnienie | Zapoznanie się z propozycją |
| Checkout czeka na zgodę | Dokładny rachunek i warunki | Świadome zatwierdzenie |
| Trwa zakup | Informacja o zabezpieczaniu zgody, płatności i zamówienia | Oczekiwanie na autorytatywny wynik |
| Zamówienie potwierdzone | Numer zamówienia, płatność, dostawa | Śledzenie lub anulowanie, jeśli możliwe |
| Zamówienie dostarczone | Stan dostarczenia | Rozpoczęcie zwrotu |
| Transakcja rozwiązana | Anulowanie albo refundacja zakończona | Wgląd w historię i kwotę zwrotu |
| Błąd | Bezpieczny opis problemu | Powrót, odświeżenie lub nowa próba zależnie od sytuacji |

## 8. Model zaufania i kontroli

Produkt buduje zaufanie poprzez rozdzielenie rozmowy od konsekwencji finansowych.

### Agent może

- interpretować język naturalny;
- porównywać znaczenie ofert;
- wybierać i wyjaśniać;
- proponować kolejne działania;
- koordynować obsługę wyjątku.

### Agent nie może samodzielnie

- ustalić autorytatywnej ceny;
- ogłosić dostępności produktu;
- stworzyć zgody użytkownika;
- zwiększyć limitu wydatków;
- zmienić zakres płatności;
- uznać zamówienia za potwierdzone bez odpowiedzi sprzedawcy;
- uznać refundacji za zakończoną bez potwierdzenia finansowego.

### Użytkownik powinien zawsze móc odpowiedzieć na pytania

- Co agent zrozumiał z mojej prośby?
- Dlaczego wybrał właśnie ten produkt?
- Jakie alternatywy odrzucił i dlaczego?
- Co dokładnie zatwierdziłem?
- Ile pieniędzy zarezerwowano, pobrano lub zwrócono?
- Czy istnieje potwierdzone zamówienie?
- Co aktualnie dzieje się z dostawą?
- Jaki jest kolejny krok w anulowaniu lub zwrocie?

## 9. Granice obecnego produktu

Obecna wersja jest skoncentrowana na jednym wiarygodnym pionowym scenariuszu, a nie na szerokości katalogu. Demonstracyjny sprzedawca i mały zestaw produktów służą udowodnieniu mechanizmu transakcyjnego.

Świadomie poza głównym zakresem pozostają między innymi:

- duży marketplace i rozbudowane przeglądanie katalogu;
- scraping stron sklepów;
- wiele niezależnych agentów współpracujących przy jednym zakupie;
- przechowywanie prawdziwych danych kart przez agenta;
- produkcyjna obsługa tożsamości, podatków, fraudu i logistyki;
- wiele równoległych protokołów płatniczych;
- zaawansowany silnik rekomendacji jako główna wartość produktu.

Płatność demonstracyjna odtwarza realistyczne stany autoryzacji, pobrania, odrzucenia, zwolnienia i refundacji, ale nie jest jeszcze pełnym konsumenckim doświadczeniem realnego dostawcy płatności.

## 10. Obecne mocne strony doświadczenia

1. **Pełny lifecycle zamiast rekomendacji.** Produkt prowadzi od potrzeby aż do rozwiązania problemu po zakupie.
2. **Jedna ciągła historia.** Intencja, zgoda, zamówienie i refundacja pozostają w tej samej rozmowie.
3. **Wyraźna granica zgody.** Użytkownik zatwierdza dokładną propozycję, a nie abstrakcyjną intencję.
4. **Autorytatywny sukces.** Interfejs nie ogłasza zakupu przed potwierdzeniem zamówienia.
5. **Semantyczne dopasowanie.** Agent może rozumieć różne nazwy tej samej właściwości produktu bez sztywnego słownika synonimów.
6. **Obiektywne reguły poza modelem.** Cena, stock, dostawa i zwroty są chronione przed swobodną interpretacją.
7. **Odporność na ponowienia i niejasne wyniki.** System minimalizuje ryzyko podwójnego obciążenia lub zamówienia.
8. **Powrót do transakcji.** Użytkownik może prowadzić wiele rozmów i wracać do ich aktualnego stanu.
9. **Widoczna aktywność.** Praca w tle nie jest czarną skrzynką; użytkownik widzi bezpieczne etapy działania.

## 11. Obszary do analizy przez design i biznes

Poniższe punkty nie są gotową roadmapą. Są pytaniami wynikającymi z obecnego flow i mogą pomóc określić kolejne wartościowe rozszerzenia.

### 11.1. Co dzieje się po braku dopasowania?

Obecny flow poprawnie zatrzymuje zakup, lecz ma ograniczone działania następcze. Warto rozważyć:

- wskazanie warunku, który wykluczył najwięcej ofert;
- kontrolowane poluzowanie tylko jednego wymagania;
- zgodę na substytucję;
- alert, gdy pojawi się właściwy produkt;
- rozszerzenie wyszukiwania na kolejnych sprzedawców;
- prezentację „najbliższego bezpiecznego dopasowania” bez sugerowania, że spełnia ono wszystkie warunki.

### 11.2. Jak użytkownik ma zarządzać mandatami?

Mandat jest strategiczną funkcją agentic commerce, ale wymaga osobnego doświadczenia:

- tworzenie i podgląd zakresu;
- limit na transakcję i limit okresowy;
- zarezerwowany oraz wykorzystany budżet;
- lista agentów, kategorii i sprzedawców;
- termin ważności;
- szybkie zawieszenie lub odwołanie;
- historia zakupów wykonanych automatycznie;
- powiadomienie przed i po zakupie.

### 11.3. Jak pokazywać porównanie i pewność?

Obecnie użytkownik widzi wybrany produkt i krótkie uzasadnienie. Senior design może przeanalizować:

- czy pokazywać odrzucone alternatywy;
- jak odróżnić twardy dowód od wnioskowania agenta;
- czy procent pewności jest zrozumiały i godny zaufania;
- kiedy niski confidence powinien wywołać pytanie zamiast propozycji;
- jak pokazać kompromisy bez przeciążenia karty produktu;
- czy użytkownik powinien móc wybrać inną kwalifikującą się ofertę.

### 11.4. Adres, tożsamość i profil zakupowy

Kanoniczna intencja zawiera termin dostawy, ale pełne doświadczenie konsumenckie wymaga decyzji dotyczących:

- wyboru lub potwierdzenia adresu;
- odbiorcy i danych kontaktowych;
- preferowanej metody dostawy;
- zapisanych preferencji zakupowych;
- prywatności danych osobowych;
- sytuacji, gdy zmiana adresu zmienia cenę lub termin i wymaga ponownej zgody.

### 11.5. Powiadomienia i praca długotrwała

Agent ma działać również wtedy, gdy użytkownik nie patrzy na rozmowę. Warto ustalić:

- które zdarzenia wymagają powiadomienia;
- kiedy agent może działać automatycznie, a kiedy musi wrócić po decyzję;
- jak pokazywać opóźnienie, zmianę terminu lub próbę dostawy;
- czy użytkownik może określić preferowany kanał i poziom pilności;
- jak wznowić rozmowę po kilku dniach bez utraty kontekstu.

### 11.6. Realne wyjątki posprzedażowe

Obecny model obejmuje anulowanie, zwrot i refundację. Kolejne scenariusze biznesowe to:

- częściowy zwrot wielu produktów;
- wymiana zamiast refundacji;
- produkt uszkodzony lub niezgodny z opisem;
- niedostarczona przesyłka;
- częściowa refundacja;
- opłata restockingowa;
- spór ze sprzedawcą;
- eskalacja do człowieka;
- dokumenty, zdjęcia i dowody;
- terminy oraz SLA kolejnych etapów.

### 11.7. Status refundacji

Dokumentacja statusowa projektu wskazuje jeszcze niespójność integracyjną w śledzeniu refundacji po zdarzeniu sprzedawcy. Jednocześnie interfejs i scenariusze domenowe przewidują zakończoną refundację. Przed prezentacją biznesową należy jednoznacznie potwierdzić, który wariant działa w pełnym flow uruchamianym z UI i czy użytkownik widzi wszystkie etapy, a nie tylko wynik końcowy.

### 11.8. Wiele sklepów i porównywalność warunków

Przy większej liczbie sprzedawców pojawią się pytania:

- jak porównywać różne definicje dostawy i zwrotu;
- jak komunikować reputację oraz ryzyko sprzedawcy;
- jak uwzględniać podatki i opłaty ujawniane dopiero przy checkoutcie;
- czy agent optymalizuje cenę, termin, zaufanie czy łączną wartość;
- kiedy zmiana sprzedawcy jest materialną zmianą wymagającą nowej zgody;
- kto odpowiada za obsługę posprzedażową.

### 11.9. Kontrola użytkownika podczas pracy agenta

Do rozważenia pozostają funkcje takie jak:

- przerwanie aktywnego wyszukiwania;
- edycja wymagań bez rozpoczynania całej historii od nowa;
- zatwierdzenie kompromisu zaproponowanego przez agenta;
- zapis wersji intencji i pokazanie, co zmieniło się po doprecyzowaniu;
- odrzucenie propozycji z podaniem powodu;
- ręczny wybór spośród kilku poprawnych ofert.

### 11.10. Język, dostępność i zaufanie wizualne

Obecne komunikaty są przede wszystkim angielskie, podczas gdy kanoniczny użytkownik i waluta wskazują również na rynek polski. Potrzebne są decyzje dotyczące:

- lokalizacji całego flow;
- prezentacji walut, dat i terminów prawnych;
- prostego języka zgody;
- dostępności klawiaturowej i czytników ekranu;
- odróżnienia informacji agenta od informacji autorytatywnej;
- sposobu prezentowania błędów finansowych bez wywoływania paniki;
- projektowania na urządzenia mobilne.

## 12. Rekomendowany scenariusz prezentacji

Najpełniejsza narracja biznesowa powinna pokazać nie tylko zakup, lecz całą odpowiedzialność agenta:

1. Użytkownik wpisuje kanoniczną prośbę o monitor.
2. Interfejs pokazuje interpretację wymagań i aktywność wyszukiwania.
3. Agent odrzuca monitor niekompatybilny z Makiem i wybiera StudioView.
4. Użytkownik widzi dowód dopasowania, cenę, dostawę i zwroty.
5. Sprzedawca tworzy dokładny checkout.
6. Użytkownik zatwierdza konkretną kwotę i warunki.
7. System autoryzuje płatność, otrzymuje potwierdzenie zamówienia i dopiero wtedy pobiera środki.
8. Interfejs pokazuje numer zamówienia, płatność i oczekiwaną dostawę.
9. Status przechodzi przez realizację do dostarczenia.
10. Użytkownik rozpoczyna zwrot albo wcześniej anuluje zamówienie.
11. Refundacja jest widoczna i powiązana z pierwotnym zakupem.

Dodatkowy scenariusz powinien pokazać wartość mechanizmów zaufania, na przykład zmianę ceny po zgodzie, odrzucenie płatności albo niejasny timeout. To pozwala zaprezentować, że produkt nie jest jedynie szczęśliwą ścieżką demonstracyjną, ale projektuje odpowiedzialność za konsekwencje.

## 13. Kryterium sukcesu doświadczenia

Flow jest udany, gdy użytkownik może bez znajomości konkretnego sklepu:

- jasno opisać potrzebę;
- zrozumieć, jak agent ją zinterpretował;
- zobaczyć wiarygodne uzasadnienie wyboru;
- zatwierdzić dokładną, aktualną transakcję;
- mieć pewność, że pieniądze nie zostaną użyte poza zakresem zgody;
- otrzymać potwierdzenie realnego zamówienia;
- wrócić do zadania i zobaczyć aktualny stan;
- anulować lub zwrócić produkt zgodnie z obowiązującymi warunkami;
- prześledzić wynik finansowy aż do końca.

Najważniejszą miarą jakości nie jest liczba produktów w katalogu ani długość rozmowy. Jest nią odsetek zadań zakupowych domkniętych poprawnie, zrozumiale i bez utraty kontroli przez użytkownika — również wtedy, gdy coś zmieni się lub pójdzie niezgodnie z planem.
