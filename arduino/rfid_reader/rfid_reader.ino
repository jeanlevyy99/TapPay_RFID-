
#include <SPI.h>
#include <MFRC522.h>

// RFID reader pins
#define SS_PIN 10
#define RST_PIN 9

// Indicator pins
#define GREEN_LED 5
#define RED_LED 6
#define BUZZER 4

MFRC522 rfid(SS_PIN, RST_PIN);

bool waitingForRemoval = false;

// Turn off all indicators
void indicatorsOff() {
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(RED_LED, LOW);
  noTone(BUZZER);
}

// Play a beep
void beep(int frequency, int duration) {
  tone(BUZZER, frequency);
  delay(duration);
  noTone(BUZZER);
  delay(100);
}

// Arduino and RFID initialization
void startupSound() {
  beep(1500, 150);
}

// Card detected for registration
void newCardSound() {
  beep(1200, 120);
  beep(1600, 120);
}

// Card already registered
void existingCardSound() {
  beep(700, 300);
}

// Balance added successfully
void balanceAddedSound() {
  beep(1000, 120);
  beep(1400, 120);
  beep(1800, 200);
}

// RFID reading error
void errorSound() {
  beep(400, 500);
}

// Show payment result
void showResult(bool approved) {
  indicatorsOff();

  if (approved) {
    digitalWrite(GREEN_LED, HIGH);
    beep(1800, 180);
  } else {
    digitalWrite(RED_LED, HIGH);
    beep(450, 200);
    beep(450, 200);
  }

  delay(1000);
  indicatorsOff();
}

// Initialize Arduino and RFID reader
void setup() {
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  indicatorsOff();

  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();

  delay(100);
  Serial.println("READY");

  // One beep when the reader initializes
  startupSound();
}

// Main program
void loop() {

  // Receive commands from the Python application
  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "APPROVED") {
      showResult(true);
    }
    else if (cmd == "DECLINED") {
      showResult(false);
    }
    else if (cmd == "NEW_CARD") {
      newCardSound();
    }
    else if (cmd == "CARD_EXISTS") {
      existingCardSound();
    }
    else if (cmd == "BALANCE_ADDED") {
      balanceAddedSound();
    }
    else if (cmd == "ERROR") {
      errorSound();
    }
    else if (cmd == "RESET") {
      indicatorsOff();
    }
  }

  // Wait until the previous card is removed
  if (waitingForRemoval) {
    if (!rfid.PICC_IsNewCardPresent()) {
      waitingForRemoval = false;
      delay(150);
    }
    return;
  }

  // Detect a new card
  if (!rfid.PICC_IsNewCardPresent()) {
    return;
  }

  if (!rfid.PICC_ReadCardSerial()) {
    return;
  }
  // One beep when a card is detected
  beep(1200, 150);



  // Read physical card UID
  String uid = "";

  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) {
      uid += "0";
    }

    uid += String(rfid.uid.uidByte[i], HEX);
  }

  uid.toUpperCase();

  // Send UID to Python application
  Serial.print("CARD:");
  Serial.println(uid);
 

  // Stop communication with the card
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  // Prevent repeated reads while card remains present
  waitingForRemoval = true;
  delay(150);
}
