import 'dart:async';
import 'dart:convert';

import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

import '../models/pzem_data.dart';

class PzemDataService {
  // Temporary Raspberry Pi MQTT address.
  //
  // This should eventually be replaced with the Pi's permanent
  // address/hostname.
  static const String brokerAddress = '192.168.8.2';
  static const int brokerPort = 1883;

  // pzem_2_name.py publishes Grid and Load measurements
  // to these two MQTT topics.
  static const String gridTopic = 'pzem/ac_data_1';
  static const String loadTopic = 'pzem/ac_data_2';

  late final MqttServerClient _client;

  final StreamController<PzemData> _dataController =
  StreamController<PzemData>.broadcast();

  // Keep the newest values from both PZEM meters.
  PzemData _currentData = const PzemData(
    gridVoltage: 0.0,
    gridCurrent: 0.0,
    gridPower: 0.0,
    gridEnergy: 0.0,
    gridFrequency: 0.0,
    gridPowerFactor: 0.0,
    gridAlarmStatus: 0,

    loadVoltage: 0.0,
    loadCurrent: 0.0,
    loadPower: 0.0,
    loadEnergy: 0.0,
    loadFrequency: 0.0,
    loadPowerFactor: 0.0,
    loadAlarmStatus: 0,
  );

  bool _initialized = false;

  Stream<PzemData> get dataStream => _dataController.stream;

  PzemData get currentData => _currentData;

  Future<void> connect() async {
    if (_initialized &&
        _client.connectionStatus?.state ==
            MqttConnectionState.connected) {
      return;
    }

    final clientId =
        'flutter_pzem_${DateTime.now().millisecondsSinceEpoch}';

    _client = MqttServerClient.withPort(
      brokerAddress,
      clientId,
      brokerPort,
    );

    _client.logging(on: false);
    _client.keepAlivePeriod = 20;

    _client.onConnected = () {
      print('PZEM MQTT connected');
    };

    _client.onDisconnected = () {
      print('PZEM MQTT disconnected');
    };

    _client.connectionMessage = MqttConnectMessage()
        .withClientIdentifier(clientId)
        .startClean()
        .withWillQos(MqttQos.atMostOnce);

    try {
      await _client.connect();
    } catch (e) {
      _client.disconnect();

      throw Exception(
        'Could not connect to Raspberry Pi MQTT: $e',
      );
    }

    if (_client.connectionStatus?.state !=
        MqttConnectionState.connected) {
      throw Exception(
        'MQTT connection failed: ${_client.connectionStatus}',
      );
    }

    _initialized = true;

    // Listen to both PZEM meters.
    _client.subscribe(
      gridTopic,
      MqttQos.atMostOnce,
    );

    _client.subscribe(
      loadTopic,
      MqttQos.atMostOnce,
    );

    _client.updates?.listen(
          (List<MqttReceivedMessage<MqttMessage?>> messages) {
        if (messages.isEmpty) {
          return;
        }

        final receivedMessage = messages.first;
        final topic = receivedMessage.topic;
        final message = receivedMessage.payload;

        if (message is! MqttPublishMessage) {
          return;
        }

        final payload =
        MqttPublishPayload.bytesToStringAsString(
          message.payload.message,
        );

        _processPzemMessage(
          topic,
          payload,
        );
      },
    );
  }

  void _processPzemMessage(
      String topic,
      String payload,
      ) {
    try {
      final dynamic decoded = jsonDecode(payload);

      if (decoded is! Map<String, dynamic>) {
        return;
      }

      if (topic == gridTopic) {
        _updateGridData(decoded);
      } else if (topic == loadTopic) {
        _updateLoadData(decoded);
      }

      // Send the newest combined Grid + Load state
      // to the Flutter UI.
      _dataController.add(_currentData);
    } catch (e) {
      print(
        'Could not decode PZEM MQTT message: $e',
      );
    }
  }

  void _updateGridData(
      Map<String, dynamic> data,
      ) {
    _currentData = PzemData(
      gridVoltage:
      _toDouble(data['Grid voltage']) ??
          _currentData.gridVoltage,

      gridCurrent:
      _toDouble(data['Grid amperage']) ??
          _currentData.gridCurrent,

      gridPower:
      _toDouble(data['Grid power']) ??
          _currentData.gridPower,

      gridEnergy:
      _toDouble(data['Grid energy']) ??
          _currentData.gridEnergy,

      gridFrequency:
      _toDouble(data['Grid frequency']) ??
          _currentData.gridFrequency,

      gridPowerFactor:
      _toDouble(data['Grid powerFactor']) ??
          _currentData.gridPowerFactor,

      gridAlarmStatus:
      _toInt(data['Grid alarmStatus']) ??
          _currentData.gridAlarmStatus,

      // Keep the latest Load values unchanged.
      loadVoltage: _currentData.loadVoltage,
      loadCurrent: _currentData.loadCurrent,
      loadPower: _currentData.loadPower,
      loadEnergy: _currentData.loadEnergy,
      loadFrequency: _currentData.loadFrequency,
      loadPowerFactor: _currentData.loadPowerFactor,
      loadAlarmStatus: _currentData.loadAlarmStatus,
    );

    print(
      'Grid PZEM update: '
          'Voltage=${_currentData.gridVoltage} V, '
          'Current=${_currentData.gridCurrent} A, '
          'Power=${_currentData.gridPower} W',
    );
  }

  void _updateLoadData(
      Map<String, dynamic> data,
      ) {
    _currentData = PzemData(
      // Keep the latest Grid values unchanged.
      gridVoltage: _currentData.gridVoltage,
      gridCurrent: _currentData.gridCurrent,
      gridPower: _currentData.gridPower,
      gridEnergy: _currentData.gridEnergy,
      gridFrequency: _currentData.gridFrequency,
      gridPowerFactor: _currentData.gridPowerFactor,
      gridAlarmStatus: _currentData.gridAlarmStatus,

      loadVoltage:
      _toDouble(data['Load voltage']) ??
          _currentData.loadVoltage,

      loadCurrent:
      _toDouble(data['Load amperage']) ??
          _currentData.loadCurrent,

      loadPower:
      _toDouble(data['Load power']) ??
          _currentData.loadPower,

      loadEnergy:
      _toDouble(data['Load energy']) ??
          _currentData.loadEnergy,

      loadFrequency:
      _toDouble(data['Load frequency']) ??
          _currentData.loadFrequency,

      loadPowerFactor:
      _toDouble(data['Load powerFactor']) ??
          _currentData.loadPowerFactor,

      loadAlarmStatus:
      _toInt(data['Load alarmStatus']) ??
          _currentData.loadAlarmStatus,
    );

    print(
      'Load PZEM update: '
          'Voltage=${_currentData.loadVoltage} V, '
          'Current=${_currentData.loadCurrent} A, '
          'Power=${_currentData.loadPower} W',
    );
  }

  double? _toDouble(dynamic value) {
    if (value == null) {
      return null;
    }

    if (value is num) {
      return value.toDouble();
    }

    return double.tryParse(
      value.toString(),
    );
  }

  int? _toInt(dynamic value) {
    if (value == null) {
      return null;
    }

    if (value is int) {
      return value;
    }

    if (value is num) {
      return value.toInt();
    }

    if (value is bool) {
      return value ? 1 : 0;
    }

    return int.tryParse(
      value.toString(),
    );
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
