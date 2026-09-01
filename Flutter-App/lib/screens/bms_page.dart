import 'package:flutter/material.dart';

import '../models/bms_data.dart';
import '../services/bms_data_service.dart';

class BmsPage extends StatefulWidget {
  const BmsPage({super.key});

  @override
  State<BmsPage> createState() => _BmsPageState();
}

class _BmsPageState extends State<BmsPage> {
  final BmsDataService _bmsService = BmsDataService();

  bool _isConnecting = true;
  String? _connectionError;

  @override
  void initState() {
    super.initState();
    _connectToBms();
  }

  Future<void> _connectToBms() async {
    setState(() {
      _isConnecting = true;
      _connectionError = null;
    });

    try {
      await _bmsService.connect();

      if (!mounted) return;

      setState(() {
        _isConnecting = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _isConnecting = false;
        _connectionError = e.toString();
      });
    }
  }

  @override
  void dispose() {
    _bmsService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF25262C),

      appBar: AppBar(
        backgroundColor: const Color(0xFF465EAA),
        title: const Text(
          'BMS Data',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        actions: [
          IconButton(
            onPressed: _connectToBms,
            icon: const Icon(Icons.refresh),
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
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text(
              'Connecting to BMS...',
              style: TextStyle(color: Colors.white),
            ),
          ],
        ),
      );
    }

    if (_connectionError != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.error_outline,
                color: Colors.redAccent,
                size: 48,
              ),
              const SizedBox(height: 16),
              const Text(
                'Could not connect to BMS',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                _connectionError!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: _connectToBms,
                child: const Text('Try Again'),
              ),
            ],
          ),
        ),
      );
    }

    return StreamBuilder<BmsData>(
      stream: _bmsService.dataStream,
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const Center(
            child: Text(
              'Connected. Waiting for BMS data...',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
              ),
            ),
          );
        }

        final data = snapshot.data!;

        return ListView(
          padding: const EdgeInsets.all(16.0),
          children: [
            BmsDataCard(
              label: 'Battery Voltage',
              value: '${data.batteryVoltage.toStringAsFixed(1)} V',
              icon: Icons.battery_full,
            ),

            const SizedBox(height: 12),

            BmsDataCard(
              label: 'Battery Current',
              value: '${data.batteryCurrent.toStringAsFixed(1)} A',
              icon: Icons.electric_bolt,
            ),

            const SizedBox(height: 12),

            BmsDataCard(
              label: 'State of Charge',
              value: '${data.stateOfCharge.toStringAsFixed(1)}%',
              icon: Icons.battery_charging_full,
            ),

            const SizedBox(height: 12),

            BmsDataCard(
              label: 'State of Health',
              value: '${data.stateOfHealth.toStringAsFixed(1)}%',
              icon: Icons.favorite,
            ),

            const SizedBox(height: 12),

            BmsDataCard(
              label: 'Battery Temperature',
              value: '${data.batteryTemperature.toStringAsFixed(1)} °C',
              icon: Icons.thermostat,
            ),
          ],
        );
      },
    );
  }
}

class BmsDataCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;

  const BmsDataCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),

      decoration: BoxDecoration(
        color: const Color(0xFF30313A),
        borderRadius: BorderRadius.circular(10),
      ),

      child: Row(
        children: [
          Icon(
            icon,
            size: 36,
            color: const Color(0xFF25C99A),
          ),

          const SizedBox(width: 16),

          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 18,
                color: Colors.white,
              ),
            ),
          ),

          Text(
            value,
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: Color(0xFFB9FF26),
            ),
          ),
        ],
      ),
    );
  }
}
