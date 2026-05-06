import { useEffect, useRef } from 'react';

let googleMapsPromise;

function loadGoogleMaps() {
  if (window.google?.maps) return Promise.resolve(window.google);

  if (!googleMapsPromise) {
    const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
    googleMapsPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=${key}`;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve(window.google);
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  return googleMapsPromise;
}

export default function OfficeLocationMap({ office, onPick }) {
  const mapRef = useRef(null);

  useEffect(() => {
    let map;
    let marker;
    let circle;

    async function init() {
      const google = await loadGoogleMaps();

      const center = {
        lat: Number(office.latitude) || -26.2041,
        lng: Number(office.longitude) || 28.0473,
      };

      map = new google.maps.Map(mapRef.current, {
        center,
        zoom: office.latitude && office.longitude ? 17 : 12,
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
    }

    init();
  }, [office]);

  return <div style={{ height: 300, width: '100%', borderRadius: 16, overflow: 'hidden' }} ref={mapRef} />;
}