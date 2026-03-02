import React from 'react';
import VideoTemplate, { VideoTemplateProps } from '../VideoTemplate';

export default function FoodShowcase(props: VideoTemplateProps) {
  return (
    <VideoTemplate
      {...props}
      transition="fade"
      style={{
        ...props.style,
        primaryColor: '#FFD700',
        secondaryColor: '#FF8C00',
        overlayOpacity: 0.5,
      }}
    />
  );
}
