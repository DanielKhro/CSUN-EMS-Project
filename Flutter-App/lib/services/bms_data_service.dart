import 'dart:async';
import 'dart:convert';

import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

import '../models/bms_data.dart';

class BmsDataService {
  // Raspberry Pi MQTT broker.
  //
  // IMPORTANT:
  // This is temporary until the Pi team gives the Raspberry Pi
  // a permanent/static IP address.
  static const String brokerAddress = '192.168.8.2';
  static const int brokerPort = 1883;

  // pylontec.py publishes the Pylontech BMS data underneath
  // solar/battery/.
  static const String bmsTopic = 'solar/battery/#';

  late final MqttServerClient _client;

  final StreamController<BmsData> _dataController =
  StreamController<BmsData>.broadcast();

  // Latest known values.
  //
  // The BMS sends its information in multiple MQTT messages,
  // so we keep the newest value of every field.
  BmsData _currentData = const BmsData(
    stateOfCharge: 0.0,
    stateOfHealth: 0.0,
    batteryVoltage: 0.0,
    batteryCurrent: 0.0,
    batteryTemperature: 0.0,
  );

  bool _initialized = false;

  Stream<BmsData> get dataStream => _dataController.stream;

  BmsData get currentData => _currentData;

  Future<void> connect() async {
    if (_initialized &&
        _client.connectionStatus?.state ==
            MqttConnectionState.connected) {
      return;
    }

    final clientId =
        'flutter_bms_${DateTime.now().millisecondsSinceEpoch}';

    _client = MqttServerClient.withPort(
      brokerAddress,
      clientId,
      brokerPort,
    );

    _client.logging(on: false);
    _client.keepAlivePeriod = 20;

    _client.onConnected = () {
      print('BMS MQTT connected');
    };

    _client.onDisconnected = () {
      print('BMS MQTT disconnected');
    };

    _client.connectionMessage = MqttConnectMessage()
        .withClientIdentifier(clientId)
        .startClean()
        .withWillQos(MqttQos.atMostOnce);

    try {
      await _client.connect();
    } catch (e) {
      _client.disconnect();
      throw Exception('Could not connect to Raspberry Pi MQTT: $e');
    }

    if (_client.connectionStatus?.state !=
        MqttConnectionState.connected) {
      throw Exception(
        'MQTT connection failed: ${_client.connectionStatus}',
      );
    }

    _initialized = true;

    // Listen to every Pylontech battery MQTT message.
    _client.subscribe(
      bmsTopic,
      MqttQos.atMostOnce,
    );

    _client.updates?.listen(
          (List<MqttReceivedMessage<MqttMessage?>> messages) {
        if (messages.isEmpty) {
          return;
        }

        final message = messages.first.payload;

        if (message is! MqttPublishMessage) {
          return;
        }

        final payload =
        MqttPublishPayload.bytesToStringAsString(
          message.payload.message,
        );

        _processBmsMessage(payload);
      },
    );
  }

  void _processBmsMessage(String payload) {
    try {
      final dynamic decoded = jsonDecode(payload);

      if (decoded is! Map<String, dynamic>) {
        return;
      }

      // Keep the old value if this particular MQTT message
      // does not contain that BMS measurement.
      final double soc =
          _toDouble(decoded['SOC']) ??
              _currentData.stateOfCharge;

      final double soh =
          _toDouble(decoded['SOH']) ??
              _currentData.stateOfHealth;

      final double voltage =
          _toDouble(decoded['Battery_Voltage']) ??
              _currentData.batteryVoltage;

      final double current =
          _toDouble(decoded['Battery_Current']) ??
              _currentData.batteryCurrent;

      final double temperature =
          _toDouble(decoded['Battery_Temperature']) ??
              _currentData.batteryTemperature;

      _currentData = BmsData(
        stateOfCharge: soc,
        stateOfHealth: soh,
        batteryVoltage: voltage,
        batteryCurrent: current,
        batteryTemperature: temperature,
      );

      // Send the newest complete BMS state to the Flutter UI.
      _dataController.add(_currentData);

      print(
        'BMS update: '
            'SOC=$soc%, '
            'SOH=$soh%, '
            'Voltage=$voltage V, '
            'Current=$current A, '
            'Temperature=$temperature C',
      );
    } catch (e) {
      print('Could not decode BMS MQTT message: $e');
    }
  }

  double? _toDouble(dynamic value) {
    if (value == null) {
      return null;
    }

    if (value is num) {
      return value.toDouble();
    }

    return double.tryParse(value.toString());
  }

  void disconnect() {
    if (_initialized) {
      _client.disconnect();
      _initialized = false;
    }
  }

  void dispose() {
    disconnect();
    _dataController.close();
  }
}
