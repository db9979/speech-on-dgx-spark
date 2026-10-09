# Privacy policy of the iPhone app "Spark"

Last updated: 9 October 2026

The "Spark" app is the iPhone front end for a voice assistant you run yourself on your own computer ("your Spark"). The app only works together with your Spark.

## In short

- The app talks only to your own Spark. There is no developer server.
- The developer receives no data: no usage statistics, no ads, no tracking, no crash reports through own services.
- Whoever runs the Spark is responsible for the data stored on it.

## What goes where

| What | Where | Why |
|---|---|---|
| Voice recordings and typed questions | your Spark | speech recognition and answer |
| Text from photos and documents | your Spark, only the recognised text | question about it, or "My documents" if you choose |
| Content shared via "Share → Spark" | your Spark, only the text | question about it, or store it |
| Profile settings (voice, answer length, hints) | your Spark | your settings |
| Device token for notifications | your Spark, from there to Apple | notifications on the iPhone |

The connection to your Spark is encrypted (https). The pairing key is kept in the iPhone's keychain.

## What stays on the iPhone

- **Wake word**: "Hey Spark" is recognised on the iPhone only; nothing goes to Apple or your Spark until you speak.
- **Camera and photos**: the iPhone reads the text itself. Images never leave the iPhone.
- **Contacts**: only to find the number for "Call …". Contacts are not sent to your Spark.
- **Reminders**: after your "yes" the app writes entries into the Reminders app. It reads nothing there for your Spark.
- **Questions while offline**: at most 10 typed questions wait on the iPhone for up to one day.

## Notifications through Apple

If you turn notifications on, your Spark sends only the fixed sentence "Neue Nachricht vom Spark" and a random number through Apple's push service. The iPhone then fetches the actual text directly from your Spark. Apple does not see the content.

## Deleting

"Unpair" in the app deletes the pairing key, waiting questions and the reminder mapping on the iPhone. Data on your Spark is deleted in your Spark's panel. Deleting the app removes all of its data from the iPhone.

## Children

The app is not directed at children under 13.

## Contact

Questions about the app: https://github.com/db9979/speech-on-dgx-spark/issues
