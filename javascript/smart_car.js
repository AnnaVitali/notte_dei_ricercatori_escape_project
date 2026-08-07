function Tracking_Smart () {
    value = MiniCar.LineTracking()
    if (value == 1) {
        MiniCar.motor(Motorlist.M1, Direction1.Forward, 70)
        MiniCar.motor(Motorlist.M2, Direction1.Backward, 70)
    } else if (value == 2) {
        MiniCar.motor(Motorlist.M1, Direction1.Backward, 70)
        MiniCar.motor(Motorlist.M2, Direction1.Forward, 70)
    } else if (value == 3) {
        MiniCar.motor(Motorlist.M1, Direction1.Forward, 70)
        MiniCar.motor(Motorlist.M2, Direction1.Forward, 70)
    } else {
        MiniCar.motor(Motorlist.M1, Direction1.Forward, 0)
        MiniCar.motor(Motorlist.M2, Direction1.Forward, 0)
        isLineTrackingActive = false
    }
}
function Speed_buffer() {
    MiniCar.motor(Motorlist.M1, Direction1.Forward, 50)
    MiniCar.motor(Motorlist.M2, Direction1.Forward, 50)
    basic.pause(100)
    MiniCar.motor(Motorlist.M1, Direction1.Forward, 80)
    MiniCar.motor(Motorlist.M2, Direction1.Forward, 80)
    basic.pause(100)
    MiniCar.motor(Motorlist.M1, Direction1.Forward, 110)
    MiniCar.motor(Motorlist.M2, Direction1.Forward, 110)
    basic.pause(100)
}
bluetooth.onBluetoothConnected(function () {
    basic.showIcon(IconNames.Heart)
    connected = 1
    while (connected == 1) {
        data = bluetooth.uartReadUntil(serial.delimiters(Delimiters.Hash))
        if (data == "GREEN") {
            MiniCar.led_rgb(LED_rgb_L_R.LED_R, LED_color.green1)
            MiniCar.led_rgb(LED_rgb_L_R.LED_L, LED_color.green1)
        } else if (data == "ORANGE") {
            MiniCar.led_rgb(LED_rgb_L_R.LED_R, LED_color.yellow)
            MiniCar.led_rgb(LED_rgb_L_R.LED_L, LED_color.yellow)
        } else if (data == "RED") {
            MiniCar.led_rgb(LED_rgb_L_R.LED_R, LED_color.red1)
            MiniCar.led_rgb(LED_rgb_L_R.LED_L, LED_color.red1)
        } else {
        	
        }
    }
})
bluetooth.onBluetoothDisconnected(function () {
    basic.showIcon(IconNames.Sad)
})
function isMovementButton (buttonCode: number) {
    return buttonCode == IR_FORWARD || buttonCode == IR_BACKWARD || buttonCode == IR_LEFT || buttonCode == IR_RIGHT
}
function readNewRemoteCommand () {
    buttonCode = irRemote.returnIrButton()
    
    // If no signal, count consecutive zeros to detect button release
    if (buttonCode == 0) {
        irZeroReads += 1
        if (irZeroReads >= IR_RELEASE_READS) {
            irReady = true
        }
        return
    }
    
    // Reset zero counter when any signal appears
    irZeroReads = 0
    
    // Only accept valid buttons when ready
    let isValidButton = isMovementButton(buttonCode) || buttonCode == IR_OK
    if (!isValidButton || !irReady) {
        buttonCode = 0
        return
    }
    
    // Accept this press and block further presses
    irReady = false
}
let irReady = true
let irZeroReads = 0
let data = ""
let connected = 0
let value = 0
let buttonCode = 0
let IR_RIGHT = 0
let IR_LEFT = 0
let IR_BACKWARD = 0
let IR_FORWARD = 0
let IR_OK = 0
let IR_RELEASE_READS = 3
let lastButtonTime = 0
let isLineTrackingActive = false
let LINE_TRACKING_SPEED = 70
let STOP_SPEED = 0
let FORWARD_BACKWARD_SPEED = 200
let LEFT_RIGHT_SPEED = 100
IR_FORWARD = 70
IR_BACKWARD = 21
IR_LEFT = 68
IR_RIGHT = 67
IR_OK = 64
buttonCode = 0


MiniCar.LED_OFF()
irRemote.connectInfrared(DigitalPin.P16)

basic.forever(function () {
    readNewRemoteCommand()
    
    // Toggle line tracking mode when OK is pressed
    if (buttonCode == IR_OK) {
        isLineTrackingActive = !(isLineTrackingActive)
        buttonCode = 0
    }
    
    // If line tracking is active, run it continuously
    if (isLineTrackingActive) {
        Tracking_Smart()
    } else if (buttonCode == IR_FORWARD) {
        //Speed_buffer()
        MiniCar.motor(Motorlist.M1, Direction1.Forward, 150)
        MiniCar.motor(Motorlist.M2, Direction1.Forward, 150)
        basic.pause(100)
        MiniCar.motor(Motorlist.M1, Direction1.Backward, 0)
        MiniCar.motor(Motorlist.M2, Direction1.Backward, 0)
    } else if (buttonCode == IR_BACKWARD) {
        MiniCar.motor(Motorlist.M1, Direction1.Backward, 150)
        MiniCar.motor(Motorlist.M2, Direction1.Backward, 150)
        basic.pause(100)
        MiniCar.motor(Motorlist.M1, Direction1.Backward, 0)
        MiniCar.motor(Motorlist.M2, Direction1.Backward, 0)
    } else if (buttonCode == IR_LEFT) {
        MiniCar.motor(Motorlist.M1, Direction1.Backward, 100)
        MiniCar.motor(Motorlist.M2, Direction1.Forward, 100)
        basic.pause(100)
        MiniCar.motor(Motorlist.M1, Direction1.Backward, 0)
        MiniCar.motor(Motorlist.M2, Direction1.Backward, 0)
    } else if (buttonCode == IR_RIGHT) {
        MiniCar.motor(Motorlist.M1, Direction1.Forward, 100)
        MiniCar.motor(Motorlist.M2, Direction1.Backward, 100)
        basic.pause(100)
        MiniCar.motor(Motorlist.M1, Direction1.Backward, 0)
        MiniCar.motor(Motorlist.M2, Direction1.Backward, 0)
    }
})
