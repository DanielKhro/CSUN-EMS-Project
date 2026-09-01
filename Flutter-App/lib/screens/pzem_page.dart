import 'package:flutter/material.dart';

import '../models/pzem_data.dart';
import '../services/pzem_data_service.dart';

class PzemPage extends StatefulWidget {
  const PzemPage({super.key});

  @override
  State<PzemPage> createState() => _PzemPageState();
}

class _PzemPageState extends State<PzemPage> {
  final PzemDataService _pzemService =
  PzemDataService();

  bool _isConnecting = true;
  String? _connectionError;

  @override
  void initState() {
    super.initState();

    _connectToPzem();
  }

  Future<void> _connectToPzem() async {
    setState(() {
      _isConnecting = true;
      _connectionError = null;
    });

    try {
      await _pzemService.connect();

      if (!mounted) {
        return;
      }

      setState(() {
        _isConnecting = false;
      });
    } catch (e) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isConnecting = false;
        _connectionError = e.toString();
      });
    }
  }

  @override
  void dispose() {
    _pzemService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'PZEM Measurements',
        ),
        actions: [
          IconButton(
            onPressed: _connectToPzem,
            icon: const Icon(
              Icons.refresh,
            ),
            tooltip: 'Reconnect',
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isConnecting) {
      return const Center(
        child: Column(
          mainAxisAlignment:
          MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text(
              'Connecting to PZEM...',
            ),
          ],
        ),
      );
    }

    if (_connectionError != null) {
      return Center(
        child: Padding(
          padding:
          const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment:
            MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.error_outline,
                color: Colors.red,
                size: 48,
              ),
              const SizedBox(height: 16),
              const Text(
                'Could not connect to PZEM',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight:
                  FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                _connectionError!,
                textAlign:
                TextAlign.center,
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed:
                _connectToPzem,
                child: const Text(
                  'Try Again',
                ),
              ),
            ],
          ),
        ),
      );
    }

    return StreamBuilder<PzemData>(
      stream:
      _pzemService.dataStream,
      builder: (
          context,
          snapshot,
          ) {
        if (!snapshot.hasData) {
          return const Center(
            child: Text(
              'Connected. Waiting for PZEM data...',
            ),
          );
        }

        final PzemData data =
        snapshot.data!;

        return ListView(
          padding:
          const EdgeInsets.all(16),
          children: [
            _buildSectionTitle(
              'Grid Measurements',
            ),

            _buildMeasurementTile(
              label: 'Voltage',
              value:
              data.gridVoltage,
              unit: 'V',
            ),

            _buildMeasurementTile(
              label: 'Current',
              value:
              data.gridCurrent,
              unit: 'A',
            ),

            _buildMeasurementTile(
              label: 'Power',
              value:
              data.gridPower,
              unit: 'W',
            ),

            _buildMeasurementTile(
              label: 'Energy',
              value:
              data.gridEnergy,
              unit: 'Wh',
            ),

            _buildMeasurementTile(
              label: 'Frequency',
              value:
              data.gridFrequency,
              unit: 'Hz',
            ),

            _buildMeasurementTile(
              label: 'Power Factor',
              value:
              data.gridPowerFactor,
              unit: '',
            ),

            _buildAlarmTile(
              label: 'Alarm Status',
              alarmStatus:
              data.gridAlarmStatus,
            ),

            const SizedBox(
              height: 24,
            ),

            _buildSectionTitle(
              'Load Measurements',
            ),

            _buildMeasurementTile(
              label: 'Voltage',
              value:
              data.loadVoltage,
              unit: 'V',
            ),

            _buildMeasurementTile(
              label: 'Current',
              value:
              data.loadCurrent,
              unit: 'A',
            ),

            _buildMeasurementTile(
              label: 'Power',
              value:
              data.loadPower,
              unit: 'W',
            ),

            _buildMeasurementTile(
              label: 'Energy',
              value:
              data.loadEnergy,
              unit: 'Wh',
            ),

            _buildMeasurementTile(
              label: 'Frequency',
              value:
              data.loadFrequency,
              unit: 'Hz',
            ),

            _buildMeasurementTile(
              label: 'Power Factor',
              value:
              data.loadPowerFactor,
              unit: '',
            ),

            _buildAlarmTile(
              label: 'Alarm Status',
              alarmStatus:
              data.loadAlarmStatus,
            ),
          ],
        );
      },
    );
  }

  Widget _buildSectionTitle(
      String title,
      ) {
    return Padding(
      padding:
      const EdgeInsets.only(
        bottom: 8,
      ),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 22,
          fontWeight:
          FontWeight.bold,
        ),
      ),
    );
  }

  Widget _buildMeasurementTile({
    required String label,
    required double value,
    required String unit,
  }) {
    final String displayedValue =
    unit.isEmpty
        ? value.toStringAsFixed(2)
        : '${value.toStringAsFixed(2)} $unit';

    return Card(
      child: ListTile(
        title: Text(label),
        trailing: Text(
          displayedValue,
          style: const TextStyle(
            fontSize: 18,
            fontWeight:
            FontWeight.bold,
          ),
        ),
      ),
    );
  }

  Widget _buildAlarmTile({
    required String label,
    required int alarmStatus,
  }) {
    final bool alarmActive =
        alarmStatus != 0;

    return Card(
      child: ListTile(
        title: Text(label),
        trailing: Text(
          alarmActive
              ? 'ALARM'
              : 'Normal',
          style: TextStyle(
            fontSize: 18,
            fontWeight:
            FontWeight.bold,
            color: alarmActive
                ? Colors.red
                : Colors.green,
          ),
        ),
      ),
    );
  }
}
