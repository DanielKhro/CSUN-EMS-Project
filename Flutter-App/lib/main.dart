import 'package:flutter/material.dart';

import 'screens/load_prediction_page.dart';
import 'screens/pzem_page.dart';
import 'screens/relays_page.dart';
import 'screens/bms_page.dart';

void main() {
  runApp(const EnergyManagementApp());
}

class EnergyManagementApp extends StatelessWidget {
  const EnergyManagementApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Energy Management',
      theme: ThemeData.dark(),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF202126),
      appBar: AppBar(
        backgroundColor: const Color(0xFF202126),
        title: const Text(
          'Energy Management',
          style: TextStyle(
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: GridView.count(
          crossAxisCount: 2,
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          childAspectRatio: 1,
          children: [
            DashboardButton(
              title: 'Load Prediction',
              icon: Icons.show_chart,
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) =>
                    const LoadPredictionPage(),
                  ),
                );
              },
            ),

            DashboardButton(
              title: 'PZEM',
              icon: Icons.electric_meter,
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const PzemPage(),
                  ),
                );
              },
            ),

            DashboardButton(
              title: 'Relays',
              icon: Icons.toggle_on,
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const RelayPage(),
                  ),
                );
              },
            ),

            DashboardButton(
              title: 'BMS Data',
              icon: Icons.battery_charging_full,
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const BmsPage(),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class DashboardButton extends StatelessWidget {
  final String title;
  final IconData icon;
  final VoidCallback onPressed;

  const DashboardButton({
    super.key,
    required this.title,
    required this.icon,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFF30313A),
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onPressed,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const Spacer(),
              Center(
                child: Icon(
                  icon,
                  size: 65,
                  color: const Color(0xFF25C99A),
                ),
              ),
              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }
}