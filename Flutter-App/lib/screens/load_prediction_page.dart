import 'package:flutter/material.dart';

class LoadPredictionPage extends StatelessWidget {
  const LoadPredictionPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF25262C),

      appBar: AppBar(
        backgroundColor: const Color(0xFF465EAA),
        title: const Text(
          'Load Prediction',
          style: TextStyle(
            fontWeight: FontWeight.bold,
          ),
        ),
      ),

      body: ListView(
        padding: const EdgeInsets.all(16.0),
        children: const [

          PredictionCard(
            label: 'Grid Voltage',
            value: '0.0 V',
            icon: Icons.bolt,
          ),

          SizedBox(height: 12),

          PredictionCard(
            label: 'Grid Power',
            value: '0.0 W',
            icon: Icons.power,
          ),

          SizedBox(height: 12),

          PredictionCard(
            label: 'Grid Power Factor',
            value: '0.00',
            icon: Icons.speed,
          ),

          SizedBox(height: 12),

          PredictionCard(
            label: 'Load Power',
            value: '49.16 W',
            icon: Icons.home,
          ),

          SizedBox(height: 12),

          PredictionCard(
            label: 'Load Power Factor',
            value: '0.00',
            icon: Icons.show_chart,
          ),

          SizedBox(height: 12),

          PredictionCard(
            label: 'Predicted Load',
            value: '49.16 W',
            icon: Icons.psychology,
          ),

        ],
      ),
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
      padding: const EdgeInsets.all(16.0),

      decoration: BoxDecoration(
        color: const Color(0xFF30313A),
        borderRadius: BorderRadius.circular(10.0),
      ),

      child: Row(
        children: [

          Icon(
            icon,
            size: 36.0,
            color: const Color(0xFF25C99A),
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
              fontWeight: FontWeight.bold,
              color: Color(0xFFB9FF26),
            ),
          ),

        ],
      ),
    );
  }
}