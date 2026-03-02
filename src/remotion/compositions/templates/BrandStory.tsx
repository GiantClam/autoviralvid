import React from 'react';
import VideoTemplate, { VideoTemplateProps } from '../VideoTemplate';

export default function BrandStory(props: VideoTemplateProps) {
  return (
    <VideoTemplate
      {...props}
      transition="fade"
      style={{
        ...props.style,
        primaryColor: '#E8D5B5',
        overlayOpacity: 0.7,
        subtitleFontSize: 32,
      }}
    />
  );
}
