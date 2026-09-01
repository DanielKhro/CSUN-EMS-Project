import 'package:flutter/material.dart';

import '../models/prediction_data.dart';
import '../services/prediction_data_service.dart';

class LoadPredictionPage extends StatefulWidget {
  const LoadPredictionPage({super.key});

  @override
  State<LoadPredictionPage> createState() =>
      _LoadPredictionPageState();
}

class _LoadPredictionPageState
    extends State<LoadPredictionPage> {

  final PredictionDataService _predictionService =
  PredictionDataService();

  bool _isConnecting = true;
  String? _connectionError;

  @override
  void initState() {
    super.initState();
    _connectToPredictionData();
  }

  Future<void> _connectToPredictionData() async {
    setState(() {
      _isConnecting = true;
      _connectionError = null;
    });

    try {
      await _predictionService.connect();

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
    _predictionService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor:
      const Color(0xFF25262C),

      appBar: AppBar(
        backgroundColor:
        const Color(0xFF465EAA),

        title: const Text(
          'Load Prediction',
          style: TextStyle(
            fontWeight: FontWeight.bold,
          ),
        ),

        actions: [
          IconButton(
            onPressed:
            _connectToPredictionData,
            icon:
            const Icon(Icons.refresh),
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
              'Connecting to prediction data...',
              style: TextStyle(
                color: Colors.white,
              ),
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
                color: Colors.redAccent,
                size: 48,
              ),

              const SizedBox(height: 16),

              const Text(
                'Could not connect to EMS data',
                style: TextStyle(
                  color: Colors.white,
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
                style: const TextStyle(
                  color: Colors.white70,
                ),
              ),

              const SizedBox(height: 20),

              ElevatedButton(
                onPressed:
                _connectToPredictionData,
                child:
                const Text('Try Again'),
              ),
            ],
          ),
        ),
      );
    }

    return StreamBuilder<PredictionData>(
      stream:
      _predictionService.dataStream,

      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const Center(
            child: Text(
              'Connected. Waiting for prediction data...',
              style: TextStyle(
                color: Colors.white,
              ),
            ),
          );
        }

        final PredictionData data =
        snapshot.data!;

        return ListView(
          padding:
          const EdgeInsets.all(16.0),

          children: [
            PredictionCard(
              label: 'Grid Voltage',
              value:
              '${data.gridVoltage.toStringAsFixed(1)} V',
              icon: Icons.bolt,
            ),

            const SizedBox(height: 12),

            PredictionCard(
              label: 'Grid Power',
              value:
              '${data.gridPower.toStringAsFixed(1)} W',
              icon: Icons.power,
            ),

            const SizedBox(height: 12),

            PredictionCard(
              label: 'Grid Power Factor',
              value:
              data.gridPowerFactor.toStringAsFixed(2),
              icon: Icons.speed,
            ),

            const SizedBox(height: 12),

            PredictionCard(
              label: 'Load Power',
              value:
              '${data.loadPower.toStringAsFixed(1)} W',
              icon: Icons.home,
            ),

            const SizedBox(height: 12),

            PredictionCard(
              label: 'Load Power Factor',
              value:
              data.loadPowerFactor.toStringAsFixed(2),
              icon: Icons.show_chart,
            ),

            const SizedBox(height: 12),

            PredictionCard(
              label: 'Predicted Load',
              value:
              '${data.predictedLoad.toStringAsFixed(1)} W',
              icon: Icons.psychology,
            ),
          ],
        );
      },
    );
  }
}

class PredictionCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;

  const PredictionCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding:
      const EdgeInsets.all(16.0),

      decoration: BoxDecoration(
        color:
        const Color(0xFF30313A),
        borderRadius:
        BorderRadius.circular(10.0),
      ),

      child: Row(
        children: [
          Icon(
            icon,
            size: 36.0,
            color:
            const Color(0xFF25C99A),
          ),

          const SizedBox(width: 16.0),

          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 18.0,
                color: Colors.white,
              ),
            ),
          ),

          Text(
            value,
            style: const TextStyle(
              fontSize: 20.0,
              fontWeight:
              FontWeight.bold,
              color:
              Color(0xFFB9FF26),
            ),
          ),
        ],
      ),
    );
  }
}
