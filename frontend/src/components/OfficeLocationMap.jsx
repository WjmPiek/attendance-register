import { useEffect, useRef } from 'react';

let googleMapsPromise;

function loadGoogleMaps() {
  if (window.google?.maps) return Promise.resolve(window.google);

  if (!googleMapsPromise) {
    const apikey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

    googleMapsPromise = new Promise((resolve, reject) => {
      if (!apikey) {
        reject(new Error('Missing VITE_GOOGLE_MAPS_API_KEY'));
        return;
      }

      const existingScript = document.querySelector('script[src*="maps.googleapis.com/maps/api/js"]');
      if (existingScript) {
        existingScript.addEventListener('load', () => resolve(window.google), { once: true });
        existingScript.addEventListener('error', reject, { once: true });
        return;
      }

      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=${apikey}&libraries=places`;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve(window.google);
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  return googleMapsPromise;
}

function geocodeAddress(google, address) {
  return new Promise((resolve) => {
    if (!address || !google.maps.Geocoder) {
      resolve(null);
      return;
    }

    const geocoder = new google.maps.Geocoder();
    geocoder.geocode({ address, componentRestrictions: { country: 'ZA' } }, (results, status) => {
      if (status === 'OK' && results?.[0]?.geometry?.location) {
        resolve(results[0].geometry.location);
      } else {
        resolve(null);
      }
    });
  });
}

export default function OfficeLocationMap({ office, onPick }) {
  const mapRef = useRef(null);

  useEffect(() => {
    let map;
    let marker;
    let circle;
    let cancelled = false;

    async function init() {
      const google = await loadGoogleMaps();
      if (cancelled || !mapRef.current) return;

      const hasSavedGps = office.latitude !== null && office.latitude !== undefined && office.longitude !== null && office.longitude !== undefined;

      let center = {
        lat: Number(office.latitude) || -26.2041,
        lng: Number(office.longitude) || 28.0473,
      };

      if (!hasSavedGps && office.address) {
        const geocodedLocation = await geocodeAddress(google, office.address);
        if (cancelled) return;

        if (geocodedLocation) {
          center = {
            lat: geocodedLocation.lat(),
            lng: geocodedLocation.lng(),
          };
        }
      }

      map = new google.maps.Map(mapRef.current, {
        center,
        zoom: hasSavedGps || office.address ? 17 : 12,
      });

      marker = new google.maps.Marker({
        position: center,
        map,
        draggable: true,
      });

      circle = new google.maps.Circle({
        map,
        center,
        radius: Number(office.allowed_radius_m) || 100,
        fillOpacity: 0.15,
        strokeWeight: 2,
      });

      const setLocation = (latLng) => {
        const picked = {
          latitude: latLng.lat(),
          longitude: latLng.lng(),
          allowed_radius_m: Number(office.allowed_radius_m) || 100,
        };

        marker.setPosition(latLng);
        circle.setCenter(latLng);
        onPick(picked);
      };

      map.addListener('click', (e) => setLocation(e.latLng));
      marker.addListener('dragend', (e) => setLocation(e.latLng));

      if (!hasSavedGps && office.address) {
        onPick({
          latitude: center.lat,
          longitude: center.lng,
          allowed_radius_m: Number(office.allowed_radius_m) || 100,
        });
      }
    }

    init().catch((err) => console.error('Google Maps failed to load', err));

    return () => {
      cancelled = true;
    };
  }, [office, onPick]);

  return <div style={{ height: 300, width: '100%', borderRadius: 16, overflow: 'hidden' }} ref={mapRef} />;
}
