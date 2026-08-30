import 'package:flutter/material.dart';

import '../models/pzem_data.dart';
import '../services/pzem_data_service.dart';

class PzemPage extends StatefulWidget {
  const PzemPage({super.key});

  @override
  State<PzemPage> createState() => _PzemPageState();
}

class _PzemPageState extends State<PzemPage> {
  final PzemDataService _pzemService = PzemDataService();

  late Future<PzemData> _pzemDataFuture;

  @override
  void initState() {
    super.initState();

    // Request the placeholder PZEM data when the page first opens.
    _pzemDataFuture = _pzemService.getPzemData();
  }

  void _refreshData() {
    setState(() {
      _pzemDataFuture = _pzemService.getPzemData();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('PZEM Measurements'),
        actions: [
          IconButton(
            onPressed: _refreshData,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh data',
          ),
        ],
      ),
      body: FutureBuilder<PzemData>(
        future: _pzemDataFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(
              child: CircularProgressIndicator(),
            );
          }

          if (snapshot.hasError) {
            return Center(
              child: Text(
                'Unable to load PZEM data.\n${snapshot.error}',
                textAlign: TextAlign.center,
              ),
            );
          }

          if (!snapshot.hasData) {
            return const Center(
              child: Text('No PZEM data available.'),
            );
          }

          final PzemData data = snapshot.data!;

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _buildSectionTitle('Grid Measurements'),
              _buildMeasurementTile(
                label: 'Voltage',
                value: data.gridVoltage,
                unit: 'V',
              ),
              _buildMeasurementTile(
                label: 'Current',
                value: data.gridCurrent,
                unit: 'A',
              ),
              _buildMeasurementTile(
                label: 'Power',
                value: data.gridPower,
                unit: 'W',
              ),
              _buildMeasurementTile(
                label: 'Energy',
                value: data.gridEnergy,
                unit: 'Wh',
              ),
              _buildMeasurementTile(
                label: 'Frequency',
                value: data.gridFrequency,
                unit: 'Hz',
              ),
              _buildMeasurementTile(
                label: 'Power Factor',
                value: data.gridPowerFactor,
                unit: '',
              ),
              _buildAlarmTile(
                label: 'Alarm Status',
                alarmStatus: data.gridAlarmStatus,
              ),
              const SizedBox(height: 24),
              _buildSectionTitle('Load Measurements'),
              _buildMeasurementTile(
                label: 'Voltage',
                value: data.loadVoltage,
                unit: 'V',
              ),
              _buildMeasurementTile(
                label: 'Current',
                value: data.loadCurrent,
                unit: 'A',
              ),
              _buildMeasurementTile(
                label: 'Power',
                value: data.loadPower,
                unit: 'W',
              ),
              _buildMeasurementTile(
                label: 'Energy',
                value: data.loadEnergy,
                unit: 'Wh',
              ),
              _buildMeasurementTile(
                label: 'Frequency',
                value: data.loadFrequency,
                unit: 'Hz',
              ),
              _buildMeasurementTile(
                label: 'Power Factor',
                value: data.loadPowerFactor,
                unit: '',
              ),
              _buildAlarmTile(
                label: 'Alarm Status',
                alarmStatus: data.loadAlarmStatus,
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 22,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  Widget _buildMeasurementTile({
    required String label,
    required double value,
    required String unit,
  }) {
    final String displayedValue = unit.isEmpty
        ? value.toStringAsFixed(2)
        : '${value.toStringAsFixed(2)} $unit';

    return Card(
      child: ListTile(
        title: Text(label),
        trailing: Text(
          displayedValue,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }

  Widget _buildAlarmTile({
    required String label,
    required int alarmStatus,
  }) {
    final bool alarmActive = alarmStatus != 0;

    return Card(
      child: ListTile(
        title: Text(label),
        trailing: Text(
          alarmActive ? 'ALARM' : 'Normal',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
            color: alarmActive ? Colors.red : Colors.green,
          ),
        ),
      ),
    );
  }
}