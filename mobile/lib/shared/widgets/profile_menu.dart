import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import '../../config/theme.dart';
import '../../core/services/auth_service.dart';

class ProfileMenu extends StatelessWidget {
  final AuthService authService;
  final VoidCallback? onOpenProfile;

  const ProfileMenu({
    super.key,
    required this.authService,
    this.onOpenProfile,
  });

  @override
  Widget build(BuildContext context) {
    final user = authService.currentUser;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return PopupMenuButton<String>(
      icon: CircleAvatar(
        radius: 16,
        backgroundColor: Theme.of(context).colorScheme.primary.withOpacity(0.1),
        child: Icon(
          LucideIcons.user,
          size: 18,
          color: Theme.of(context).colorScheme.primary,
        ),
      ),
      offset: const Offset(0, 48),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isDark ? Colors.white10 : Colors.black12,
          width: 1,
        ),
      ),
      onSelected: (value) async {
        if (value == 'logout') {
          await authService.logout();
        } else if (value == 'theme') {
          themeNotifier.value = isDark ? ThemeMode.light : ThemeMode.dark;
        } else if (value == 'profile') {
          onOpenProfile?.call();
        }
      },
      itemBuilder: (context) => [
        // Profile Info Header
        PopupMenuItem(
          enabled: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                user?.name ?? 'User',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: Theme.of(context).colorScheme.onSurface.withOpacity(0.8),
                ),
              ),
              Text(
                user?.email ?? '',
                style: TextStyle(
                  fontSize: 12,
                  color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
                ),
              ),
              const Divider(height: 20),
            ],
          ),
        ),
        // Settings / Theme Toggle
        PopupMenuItem(
          value: 'profile',
          child: Row(
            children: const [
              Icon(LucideIcons.userCog, size: 18),
              SizedBox(width: 12),
              Text('Profile'),
            ],
          ),
        ),
        PopupMenuItem(
          value: 'theme',
          child: Row(
            children: [
              Icon(
                isDark ? LucideIcons.sun : LucideIcons.moon,
                size: 18,
              ),
              const SizedBox(width: 12),
              Text(isDark ? 'Switch to Light' : 'Switch to Dark'),
            ],
          ),
        ),
        // Logout
        PopupMenuItem(
          value: 'logout',
          child: Row(
            children: [
              Icon(
                LucideIcons.logOut,
                size: 18,
                color: Colors.redAccent.withOpacity(0.8),
              ),
              const SizedBox(width: 12),
              Text(
                'Logout',
                style: TextStyle(color: Colors.redAccent.withOpacity(0.8)),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
