import 'dart:async';
import 'dart:convert';

import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

import '../models/prediction_data.dart';

class PredictionDataService {
  // Temporary Raspberry Pi MQTT address.
  static const String brokerAddress = '192.168.8.2';
  static const int brokerPort = 1883;

  // Existing Raspberry Pi PZEM topics.
  static const String gridTopic = 'pzem/ac_data_1';
  static const String loadTopic = 'pzem/ac_data_2';

  // New topic that the Jetson prediction program will need to publish.
  static const String predictionTopic = 'prediction/data';

  late final MqttServerClient _client;

  final StreamController<PredictionData> _dataController =
  StreamController<PredictionData>.broadcast();

  PredictionData _currentData = const PredictionData(
    gridVoltage: 0.0,
    gridPower: 0.0,
    gridPowerFactor: 0.0,
    loadPower: 0.0,
    loadPowerFactor: 0.0,
    predictedLoad: 0.0,
  );

  bool _initialized = false;

  Stream<PredictionData> get dataStream =>
      _dataController.stream;

  PredictionData get currentData => _currentData;

  Future<void> connect() async {
    if (_initialized &&
        _client.connectionStatus?.state ==
            MqttConnectionState.connected) {
      return;
    }

    final clientId =
        'flutter_prediction_${DateTime.now().millisecondsSinceEpoch}';

    _client = MqttServerClient.withPort(
      brokerAddress,
      clientId,
      brokerPort,
    );

    _client.logging(on: false);
    _client.keepAlivePeriod = 20;

    _client.onConnected = () {
      print('Prediction MQTT connected');
    };

    _client.onDisconnected = () {
      print('Prediction MQTT disconnected');
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

    // Existing PZEM measurements.
    _client.subscribe(
      gridTopic,
      MqttQos.atMostOnce,
    );

    _client.subscribe(
      loadTopic,
      MqttQos.atMostOnce,
    );

    // Future Jetson prediction output.
    _client.subscribe(
      predictionTopic,
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

        _processMessage(
          topic,
          payload,
        );
      },
    );
  }

  void _processMessage(
      String topic,
      String payload,
      ) {
    try {
      final dynamic decoded = jsonDecode(payload);

      if (decoded is! Map<String, dynamic>) {
        return;
      }

      if (topic == gridTopic) {
        _updateGrid(decoded);
      } else if (topic == loadTopic) {
        _updateLoad(decoded);
      } else if (topic == predictionTopic) {
        _updatePrediction(decoded);
      }

      _dataController.add(_currentData);
    } catch (e) {
      print(
        'Could not decode prediction MQTT message: $e',
      );
    }
  }

  void _updateGrid(
      Map<String, dynamic> data,
      ) {
    _currentData = PredictionData(
      gridVoltage:
      _toDouble(data['Grid voltage']) ??
          _currentData.gridVoltage,

      gridPower:
      _toDouble(data['Grid power']) ??
          _currentData.gridPower,

      gridPowerFactor:
      _toDouble(data['Grid powerFactor']) ??
          _currentData.gridPowerFactor,

      loadPower:
      _currentData.loadPower,

      loadPowerFactor:
      _currentData.loadPowerFactor,

      predictedLoad:
      _currentData.predictedLoad,
    );
  }

  void _updateLoad(
      Map<String, dynamic> data,
      ) {
    _currentData = PredictionData(
      gridVoltage:
      _currentData.gridVoltage,

      gridPower:
      _currentData.gridPower,

      gridPowerFactor:
      _currentData.gridPowerFactor,

      loadPower:
      _toDouble(data['Load power']) ??
          _currentData.loadPower,

      loadPowerFactor:
      _toDouble(data['Load powerFactor']) ??
          _currentData.loadPowerFactor,

      predictedLoad:
      _currentData.predictedLoad,
    );
  }

  void _updatePrediction(
      Map<String, dynamic> data,
      ) {
    _currentData = PredictionData(
      gridVoltage:
      _currentData.gridVoltage,

      gridPower:
      _currentData.gridPower,

      gridPowerFactor:
      _currentData.gridPowerFactor,

      loadPower:
      _currentData.loadPower,

      loadPowerFactor:
      _currentData.loadPowerFactor,

      predictedLoad:
      _toDouble(data['predicted_load']) ??
          _currentData.predictedLoad,
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
