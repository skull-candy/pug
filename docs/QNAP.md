# QNAP SNMP Notes

Project repository: `https://git.vns.ae/ahsan/pug`

QNAP SNMP UPS mode probes `sysObjectID` first:

- Request: `1.3.6.1.2.1.1.2.0`
- APC identity response: `1.3.6.1.4.1.318.1.1.1`

After that, QNAP treats the endpoint as APC PowerNet and requests APC enterprise OIDs such as the model, battery charge, runtime, input voltage, output voltage, load, and battery status.

## Configure QNAP

1. Set UPS type to SNMP.
2. Enter the IP address of the Raspberry Pi or Linux host running PUG.
3. Set the community string, default `public`.
4. Apply and check that QNAP shows APC as manufacturer and the configured model.

## Known Issue

APC enum correctness matters. If AC power source or battery state values are wrong, QNAP may show confusing status even when charge/runtime values are present.
