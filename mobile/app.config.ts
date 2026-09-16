import { ConfigContext, ExpoConfig } from 'expo/config';

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'Inscrona',
  slug: 'inscrona-mobile',
  version: '1.0.0',
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'automatic',
  splash: {
    image: './assets/splash.png',
    resizeMode: 'contain',
    backgroundColor: '#0a1530'
  },
  assetBundlePatterns: ['**/*'],
  ios: {
    supportsTablet: true,
    bundleIdentifier: 'com.inscrona.teacher',
    infoPlist: {
      NSCameraUsageDescription: 'Inscrona needs camera access to photograph answer sheets',
      NSPhotoLibraryUsageDescription: 'Inscrona needs photo library access to select answer sheets',
      NSLocalNetworkUsageDescription: 'Inscrona discovers local backend on the same network'
    },
    associatedDomains: ['applinks:inscrona.app']
  },
  android: {
    adaptiveIcon: {
      foregroundImage: './assets/adaptive-icon.png',
      backgroundColor: '#0a1530'
    },
    package: 'com.inscrona.teacher',
    permissions: [
      'CAMERA',
      'READ_EXTERNAL_STORAGE',
      'WRITE_EXTERNAL_STORAGE',
      'INTERNET',
      'ACCESS_NETWORK_STATE',
      'ACCESS_WIFI_STATE'
    ]
  },
  web: {
    favicon: './assets/favicon.png'
  },
  plugins: [
    'expo-router',
    'expo-sentry',
    [
      'expo-camera',
      {
        cameraPermission: 'Allow Inscrona to access your camera to photograph answer sheets.'
      }
    ],
    [
      'expo-image-picker',
      {
        photosPermission: 'Allow Inscrona to access your photos to select answer sheets.'
      }
    ],
    [
      'expo-barcode-scanner',
      {
        cameraPermission: 'Allow Inscrona to scan QR codes for backend pairing.'
      }
    ],
    [
      'expo-splash-screen',
      {
        backgroundColor: '#0a1530',
        image: './assets/splash.png',
        dark: {
          backgroundColor: '#0a1530',
          image: './assets/splash.png'
        }
      }
    ]
  ],
  experiments: {
    typedRoutes: true,
    tsconfigPaths: true
  },
  extra: {
    eas: {
      projectId: 'inscrona-mobile'
    }
  },
  owner: 'inscrona'
});